# -*- coding: utf-8 -*-
"""
Cifrado por usuario (cifrado de sobre con clave pública).

Alternativa a la clave maestra única de :mod:`crypto`. Aquí cada archivo lleva
su propia clave de datos (DEK) aleatoria, y esa DEK se guarda **envuelta por
separado para cada persona autorizada**, usando su clave pública. Para leer, la
persona desenvuelve la DEK con su clave privada; esa clave privada solo se puede
descifrar con su contraseña. Consecuencia: un administrador que no conoce la
contraseña de nadie **no puede leer el contenido**, aunque tenga el archivo y
sus permisos NTFS.

Por qué clave pública y no un secreto compartido: compartir un archivo con otra
persona solo necesita su clave **pública**, que no es secreta. Así el dueño
puede dar acceso a alguien sin conocer su contraseña. Con claves simétricas eso
sería imposible.

------------------------------------------------------------------------------
Identidad de cada usuario
------------------------------------------------------------------------------
- Par RSA-2048. La pública se guarda en claro; cualquiera puede envolver para
  esa persona.
- La privada se guarda cifrada con AES-GCM bajo una clave derivada de la
  contraseña del usuario con scrypt (KEK). Sin la contraseña no se abre.
- Al iniciar sesión, con la contraseña a mano, se desenvuelve la privada y vive
  en memoria mientras dura la sesión. Nunca se escribe en claro.

------------------------------------------------------------------------------
Formato del archivo (versión 2)
------------------------------------------------------------------------------
Los primeros 29 bytes son idénticos al formato v1 a propósito, para que el
listado siga leyendo el tamaño real y marcando el archivo como cifrado sin
cambios:

    magia      8   b"CUSTODIA"
    version    1   0x02
    tam_claro  8   tamaño del contenido original (uint64 LE)
    nonce     12   nonce del contenido (AES-256-GCM con la DEK)
    --- fin del prefijo compatible con v1 ---
    n_dest     2   número de destinatarios (uint16 BE)
      por destinatario:
        len_u  1   + usuario (utf-8, en minúscula)
        len_w  2   + DEK envuelta con la pública del destinatario (RSA-OAEP)
    cuerpo     n   AES-256-GCM(DEK) del contenido

------------------------------------------------------------------------------
Alcance honesto
------------------------------------------------------------------------------
Sube el listón contra un administrador que quiera leer archivos ajenos: sin la
contraseña del dueño no desenvuelve ninguna DEK. No es magia: un atacante que
ejecute código mientras la víctima tiene la sesión abierta podría llegar a la
clave privada en memoria. Protege el contenido en reposo frente a quien tiene
los archivos pero no las contraseñas.
"""
from __future__ import annotations

import base64
import json
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import config, crypto
from .errors import CryptoError

VERSION = 2

_OAEP = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)

# Parámetros de scrypt para derivar la KEK de la contraseña. n=2**15 es un coste
# cómodo en un equipo de escritorio y duro para fuerza bruta.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1


# ===========================================================================
#  Núcleo criptográfico (sin estado, sin Windows: probable en cualquier parte)
# ===========================================================================

def generar_par() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def publica_a_bytes(privada_o_publica) -> bytes:
    publica = getattr(privada_o_publica, "public_key", None)
    publica = publica() if callable(publica) else privada_o_publica
    return publica.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def bytes_a_publica(der: bytes):
    return serialization.load_der_public_key(der)


def _kek(password: str, sal: bytes) -> bytes:
    return Scrypt(salt=sal, length=32, n=_SCRYPT_N, r=_SCRYPT_R,
                  p=_SCRYPT_P).derive(password.encode("utf-8"))


def envolver_privada(privada, password: str) -> tuple[bytes, bytes]:
    """Cifra la clave privada con la contraseña. Devuelve (blob, sal)."""
    sal = os.urandom(16)
    kek = _kek(password, sal)
    der = privada.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    nonce = os.urandom(12)
    cuerpo = AESGCM(kek).encrypt(nonce, der, None)
    return nonce + cuerpo, sal


def desenvolver_privada(blob: bytes, password: str, sal: bytes):
    """Recupera la clave privada. Lanza si la contraseña no corresponde."""
    kek = _kek(password, sal)
    nonce, cuerpo = blob[:12], blob[12:]
    try:
        der = AESGCM(kek).decrypt(nonce, cuerpo, None)
    except InvalidTag as exc:
        raise CryptoError("La contraseña no abre la clave privada") from exc
    return serialization.load_der_private_key(der, password=None)


def es_v2(blob: bytes) -> bool:
    return (len(blob) >= crypto.TAM_CABECERA
            and blob[:len(crypto.MAGIA)] == crypto.MAGIA
            and blob[len(crypto.MAGIA)] == VERSION)


def _desarmar(blob: bytes):
    _, version, tam_claro = crypto._CABECERA.unpack_from(blob, 0)
    if version != VERSION:
        raise CryptoError(f"No es un archivo de cifrado por usuario (v{version})")
    nonce = blob[crypto._CABECERA.size:crypto.TAM_CABECERA]
    desplazamiento = crypto.TAM_CABECERA
    (n_dest,) = struct.unpack_from(">H", blob, desplazamiento)
    desplazamiento += 2
    sobres: dict[str, bytes] = {}
    for _ in range(n_dest):
        largo_u = blob[desplazamiento]; desplazamiento += 1
        usuario = blob[desplazamiento:desplazamiento + largo_u].decode("utf-8")
        desplazamiento += largo_u
        (largo_w,) = struct.unpack_from(">H", blob, desplazamiento)
        desplazamiento += 2
        sobres[usuario] = blob[desplazamiento:desplazamiento + largo_w]
        desplazamiento += largo_w
    cuerpo = blob[desplazamiento:]
    return tam_claro, nonce, sobres, cuerpo


def _armar(tam_claro: int, nonce: bytes, sobres: dict[str, bytes],
           cuerpo: bytes) -> bytes:
    cab = crypto._CABECERA.pack(crypto.MAGIA, VERSION, tam_claro) + nonce
    cab += struct.pack(">H", len(sobres))
    for usuario, envuelta in sobres.items():
        ub = usuario.encode("utf-8")
        cab += bytes([len(ub)]) + ub + struct.pack(">H", len(envuelta)) + envuelta
    return cab + cuerpo


def cifrar(datos: bytes, destinatarios: dict[str, object]) -> bytes:
    """
    Cifra `datos` para un conjunto de destinatarios {usuario: clave_pública}.

    Genera una DEK nueva, cifra el contenido con ella y envuelve la DEK con la
    pública de cada destinatario.
    """
    if not destinatarios:
        raise CryptoError("Un archivo cifrado necesita al menos un destinatario")
    dek = os.urandom(32)
    nonce = os.urandom(crypto.TAM_NONCE)
    cuerpo = AESGCM(dek).encrypt(nonce, datos, None)
    sobres = {
        usuario.lower(): publica.encrypt(dek, _OAEP)
        for usuario, publica in destinatarios.items()
    }
    return _armar(len(datos), nonce, sobres, cuerpo)


def descifrar(blob: bytes, usuario: str, privada) -> bytes:
    """Descifra con la clave privada del usuario, si es uno de los destinatarios."""
    tam_claro, nonce, sobres, cuerpo = _desarmar(blob)
    envuelta = sobres.get(usuario.lower())
    if envuelta is None:
        raise CryptoError(
            "Tu cuenta no está entre los destinatarios de este archivo cifrado."
        )
    try:
        dek = privada.decrypt(envuelta, _OAEP)
        datos = AESGCM(dek).decrypt(nonce, cuerpo, None)
    except (InvalidTag, ValueError) as exc:
        raise CryptoError("No se pudo descifrar el archivo") from exc
    if len(datos) != tam_claro:
        raise CryptoError("El tamaño descifrado no coincide con la cabecera")
    return datos


def conceder(blob: bytes, usuario: str, privada,
             nuevo_usuario: str, nueva_publica) -> bytes:
    """
    Añade un destinatario a un archivo ya cifrado.

    Quien concede desenvuelve la DEK con su propia privada —debe ser
    destinatario— y la vuelve a envolver con la pública del nuevo. No hace falta
    la contraseña del nuevo usuario, solo su clave pública.
    """
    tam_claro, nonce, sobres, cuerpo = _desarmar(blob)
    envuelta = sobres.get(usuario.lower())
    if envuelta is None:
        raise CryptoError("Solo quien puede leer un archivo puede compartirlo.")
    dek = privada.decrypt(envuelta, _OAEP)
    sobres[nuevo_usuario.lower()] = nueva_publica.encrypt(dek, _OAEP)
    return _armar(tam_claro, nonce, sobres, cuerpo)


def destinatarios(blob: bytes) -> list[str]:
    return list(_desarmar(blob)[2].keys())


# ===========================================================================
#  Almacén de identidades (usa la ACL de Windows para protegerse)
# ===========================================================================

def _cargar_store() -> dict:
    ruta = Path(config.BOVEDA_FILE)
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text("utf-8"))
    except Exception:
        return {}


def _guardar_store(datos: dict) -> None:
    ruta = Path(config.BOVEDA_FILE)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), "utf-8")
    crypto.proteger_solo_admin(ruta)


def tiene_identidad(usuario: str) -> bool:
    return usuario.lower() in _cargar_store()


def crear_identidad(usuario: str, password: str) -> None:
    """Genera el par de claves del usuario y guarda la privada bajo su contraseña."""
    privada = generar_par()
    blob, sal = envolver_privada(privada, password)
    store = _cargar_store()
    store[usuario.lower()] = {
        "publica": base64.b64encode(publica_a_bytes(privada)).decode("ascii"),
        "privada": base64.b64encode(blob).decode("ascii"),
        "sal": base64.b64encode(sal).decode("ascii"),
    }
    _guardar_store(store)


def publica_de(usuario: str):
    entrada = _cargar_store().get(usuario.lower())
    if not entrada:
        return None
    return bytes_a_publica(base64.b64decode(entrada["publica"]))


def cambiar_contrasena(usuario: str, vieja: str, nueva: str) -> bool:
    """
    Vuelve a envolver la clave privada con la contraseña nueva. Hay que
    llamarlo al cambiar la contraseña de Windows; si no, la privada seguiría
    protegida por la vieja y los archivos cifrados para esta persona dejarían
    de abrirse. False si no hay identidad o la contraseña vieja no la abre.
    """
    privada = cargar_privada(usuario, vieja)
    if privada is None:
        return False
    blob, sal = envolver_privada(privada, nueva)
    store = _cargar_store()
    store[usuario.lower()]["privada"] = base64.b64encode(blob).decode("ascii")
    store[usuario.lower()]["sal"] = base64.b64encode(sal).decode("ascii")
    _guardar_store(store)
    return True


def cargar_privada(usuario: str, password: str):
    """Desenvuelve la clave privada con la contraseña. None si no se puede."""
    entrada = _cargar_store().get(usuario.lower())
    if not entrada:
        return None
    try:
        return desenvolver_privada(
            base64.b64decode(entrada["privada"]), password,
            base64.b64decode(entrada["sal"]),
        )
    except Exception:
        return None
