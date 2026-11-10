# -*- coding: utf-8 -*-
"""
Cifrado por usuario (cifrado de sobre con clave pública, control C20).

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
Clave de recuperación
------------------------------------------------------------------------------
Cada archivo lleva además un sobre para una clave de recuperación. Su pública
vive en este equipo; su privada, solo en la USB que guarda el dueño del
computador (ver :mod:`recuperacion`). Sin esa USB, olvidar la contraseña
significa perder los archivos.

------------------------------------------------------------------------------
Formato del archivo (versión 3)
------------------------------------------------------------------------------
Los primeros 29 bytes son idénticos al formato v1 a propósito, para que el
listado siga leyendo el tamaño real y marcando el archivo como cifrado sin
cambios:

    magia      8   b"CUSTODIA"
    version    1   0x03
    tam_claro  8   tamaño del contenido original (uint64 LE)
    nonce     12   nonce del contenido (AES-256-GCM con la DEK)
    --- fin del prefijo compatible con v1 ---
    n_dest     2   número de destinatarios (uint16 BE)
      por destinatario:
        len_u  1   + usuario (utf-8, en minúscula)
        len_w  2   + DEK envuelta con la pública del destinatario (RSA-OAEP)
    cuerpo     n   AES-256-GCM(DEK) del contenido

Toda la cabecera entra como dato autenticado de GCM: añadir un destinatario sin
conocer la DEK invalida el archivo. La versión 2 no autenticaba la cabecera; se
sigue leyendo y se convierte en la siguiente escritura o migración.

------------------------------------------------------------------------------
Alcance honesto
------------------------------------------------------------------------------
Sube el listón contra un administrador que quiera leer archivos ajenos: sin la
contraseña del dueño no desenvuelve ninguna DEK. No es magia:

- Un atacante que ejecute código mientras la víctima tiene la sesión abierta
  podría llegar a la clave privada en memoria.
- Quien tenga la USB de recuperación y su contraseña puede leer todo.
- `identidades.json` lo puede modificar un administrador. Sustituir la clave
  pública de alguien se detecta cuando esa persona entra, pero lo que otro le
  haya compartido entre tanto habrá quedado envuelto para la clave falsa.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import uuid
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import config, crypto
from .errors import CryptoError, IdentidadAlterada

VERSION = 3
_VERSIONES_SOBRE = (2, 3)

#: Nombre reservado para el sobre de la clave de recuperación. El asterisco no
#: es válido en una cuenta de Windows, así que no puede coincidir con ninguna.
RECUPERACION = "*recuperacion*"

_OAEP = padding.OAEP(
    mgf=padding.MGF1(algorithm=hashes.SHA256()),
    algorithm=hashes.SHA256(),
    label=None,
)

# scrypt para derivar la KEK. Un administrador puede copiar identidades.json y
# probar contraseñas sin conexión, y estas pueden tener solo 8 caracteres.
_SCRYPT_N = 2 ** 18
_SCRYPT_N_ANTERIOR = 2 ** 15   # entradas creadas antes de la versión 3
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


def huella(privada_o_publica) -> str:
    """SHA-256 de la clave pública, en hexadecimal."""
    return hashlib.sha256(publica_a_bytes(privada_o_publica)).hexdigest()


def _kek(password: str, sal: bytes, n: int) -> bytes:
    return Scrypt(salt=sal, length=32, n=n, r=_SCRYPT_R,
                  p=_SCRYPT_P).derive(password.encode("utf-8"))


def envolver_privada(privada, password: str, *, aad: bytes | None = None,
                     n: int | None = None) -> tuple[bytes, bytes]:
    """Cifra la clave privada con la contraseña. Devuelve (blob, sal)."""
    sal = os.urandom(16)
    kek = _kek(password, sal, n or _SCRYPT_N)
    der = privada.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    nonce = os.urandom(12)
    cuerpo = AESGCM(kek).encrypt(nonce, der, aad)
    return nonce + cuerpo, sal


def desenvolver_privada(blob: bytes, password: str, sal: bytes, *,
                        aad: bytes | None = None, n: int | None = None):
    """Recupera la clave privada. Lanza si la contraseña no corresponde."""
    kek = _kek(password, sal, n or _SCRYPT_N)
    nonce, cuerpo = blob[:12], blob[12:]
    try:
        der = AESGCM(kek).decrypt(nonce, cuerpo, aad)
    except InvalidTag as exc:
        raise CryptoError("La contraseña no abre la clave privada") from exc
    return serialization.load_der_private_key(der, password=None)


def es_v2(blob: bytes) -> bool:
    return es_sobre(blob) and blob[len(crypto.MAGIA)] == 2


def es_sobre(blob: bytes) -> bool:
    """True si el archivo usa cifrado por usuario, en cualquier versión."""
    return (len(blob) >= crypto.TAM_CABECERA
            and blob[:len(crypto.MAGIA)] == crypto.MAGIA
            and blob[len(crypto.MAGIA)] in _VERSIONES_SOBRE)


def _desarmar(blob: bytes):
    """(versión, tamaño, nonce, sobres, cuerpo, cabecera)."""
    if not es_sobre(blob):
        raise CryptoError("No es un archivo de cifrado por usuario")
    _, version, tam_claro = crypto._CABECERA.unpack_from(blob, 0)
    nonce = blob[crypto._CABECERA.size:crypto.TAM_CABECERA]
    desplazamiento = crypto.TAM_CABECERA
    try:
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
    except (struct.error, IndexError, UnicodeDecodeError) as exc:
        raise CryptoError("La cabecera del archivo cifrado está dañada") from exc
    return version, tam_claro, nonce, sobres, blob[desplazamiento:], blob[:desplazamiento]


def _armar_cabecera(tam_claro: int, nonce: bytes, sobres: dict[str, bytes]) -> bytes:
    cab = crypto._CABECERA.pack(crypto.MAGIA, VERSION, tam_claro) + nonce
    cab += struct.pack(">H", len(sobres))
    for usuario, envuelta in sobres.items():
        ub = usuario.encode("utf-8")
        cab += bytes([len(ub)]) + ub + struct.pack(">H", len(envuelta)) + envuelta
    return cab


def _sellar(dek: bytes, datos: bytes, sobres: dict[str, bytes]) -> bytes:
    """Arma un archivo v3. El nonce es nuevo siempre, aunque la DEK se repita."""
    nonce = os.urandom(crypto.TAM_NONCE)
    cabecera = _armar_cabecera(len(datos), nonce, sobres)
    return cabecera + AESGCM(dek).encrypt(nonce, datos, cabecera)


def cifrar(datos: bytes, destinatarios: dict[str, object],
           recuperacion=None) -> bytes:
    """
    Cifra `datos` para un conjunto de destinatarios {usuario: clave_pública}.

    Genera una DEK nueva, cifra el contenido con ella y envuelve la DEK con la
    pública de cada destinatario y, si se indica, con la de recuperación.
    """
    if not destinatarios:
        raise CryptoError("Un archivo cifrado necesita al menos un destinatario")
    dek = os.urandom(32)
    sobres = {
        usuario.lower(): publica.encrypt(dek, _OAEP)
        for usuario, publica in destinatarios.items()
    }
    if recuperacion is not None:
        sobres[RECUPERACION] = recuperacion.encrypt(dek, _OAEP)
    return _sellar(dek, datos, sobres)


def _dek_y_datos(blob: bytes, nombre: str, privada) -> tuple[bytes, bytes, dict]:
    """Abre el archivo con el sobre de `nombre`: (DEK, contenido, sobres)."""
    version, tam_claro, nonce, sobres, cuerpo, cabecera = _desarmar(blob)
    envuelta = sobres.get(nombre)
    if envuelta is None:
        raise CryptoError(
            "Tu cuenta no está entre los destinatarios de este archivo cifrado."
        )
    try:
        dek = privada.decrypt(envuelta, _OAEP)
        datos = AESGCM(dek).decrypt(nonce, cuerpo, cabecera if version >= 3 else None)
    except (InvalidTag, ValueError) as exc:
        raise CryptoError("No se pudo descifrar el archivo") from exc
    if len(datos) != tam_claro:
        raise CryptoError("El tamaño descifrado no coincide con la cabecera")
    return dek, datos, sobres


def descifrar(blob: bytes, usuario: str, privada) -> bytes:
    """Descifra con la clave privada del usuario, si es uno de los destinatarios."""
    return _dek_y_datos(blob, usuario.lower(), privada)[1]


def actualizar(blob: bytes, datos: bytes, usuario: str, privada,
               recuperacion=None) -> bytes:
    """
    Sustituye el contenido conservando a quienes ya tenían acceso.

    Los sobres existentes se reutilizan, así que no hay que confiar en las
    claves públicas guardadas en este equipo. Antes se verifica la cabecera: si
    alguien añadió un destinatario, aquí falla.
    """
    dek, _, sobres = _dek_y_datos(blob, usuario.lower(), privada)
    if recuperacion is not None and RECUPERACION not in sobres:
        sobres[RECUPERACION] = recuperacion.encrypt(dek, _OAEP)
    return _sellar(dek, datos, sobres)


def conceder(blob: bytes, usuario: str, privada,
             nuevo_usuario: str, nueva_publica) -> bytes:
    """
    Añade un destinatario a un archivo ya cifrado.

    Quien concede desenvuelve la DEK con su propia privada —debe ser
    destinatario— y la vuelve a envolver con la pública del nuevo. No hace falta
    la contraseña del nuevo usuario, solo su clave pública.
    """
    try:
        dek, datos, sobres = _dek_y_datos(blob, usuario.lower(), privada)
    except CryptoError as exc:
        raise CryptoError("Solo quien puede leer un archivo puede compartirlo.") from exc
    sobres[nuevo_usuario.lower()] = nueva_publica.encrypt(dek, _OAEP)
    return _sellar(dek, datos, sobres)


def reenvolver_desde_recuperacion(blob: bytes, usuario: str, privada_recuperacion,
                                  nueva_publica) -> bytes:
    """Devuelve a `usuario` el acceso a un archivo, con la clave de la USB."""
    dek, datos, sobres = _dek_y_datos(blob, RECUPERACION, privada_recuperacion)
    sobres[usuario.lower()] = nueva_publica.encrypt(dek, _OAEP)
    return _sellar(dek, datos, sobres)


def destinatarios(blob: bytes) -> list[str]:
    """Las personas con acceso; la clave de recuperación no cuenta como una."""
    return [u for u in _desarmar(blob)[3] if u != RECUPERACION]


def tiene_sobre_de_recuperacion(blob: bytes) -> bool:
    return RECUPERACION in _desarmar(blob)[3]


# ===========================================================================
#  Almacén de identidades (usa la ACL de Windows para protegerse)
# ===========================================================================

def _cargar_store() -> dict:
    """
    Lee el almacén. Si está dañado, lanza: tratarlo como vacío haría que la
    siguiente escritura borrara las identidades de todos.
    """
    ruta = Path(config.BOVEDA_FILE)
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text("utf-8"))
    except (ValueError, OSError) as exc:
        raise CryptoError("El almacén de identidades está dañado o no se puede leer.") from exc


def _guardar_store(datos: dict) -> None:
    """Escritura atómica: un corte a medias no debe perder ninguna identidad."""
    ruta = Path(config.BOVEDA_FILE)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(f"{ruta.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporal.touch()
        crypto.proteger_solo_admin(temporal)
        temporal.write_text(json.dumps(datos), "utf-8")
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)


def recuperacion_configurada() -> bool:
    return RECUPERACION in _cargar_store()


def activo() -> bool:
    """
    ¿Está en vigor el cifrado por usuario?

    Exige la clave de recuperación: sin ella, olvidar una contraseña perdería
    los archivos. Un almacén dañado cuenta como activo, para que las escrituras
    fallen en lugar de caer al cifrado con clave maestra.
    """
    if not config.CIFRADO_POR_USUARIO:
        return False
    try:
        return recuperacion_configurada()
    except CryptoError:
        return True


def configurar_recuperacion(publica) -> None:
    """Guarda la pública de recuperación. Solo una vez: cambiarla dejaría sobres huérfanos."""
    store = _cargar_store()
    if RECUPERACION in store:
        raise CryptoError("Este equipo ya tiene una clave de recuperación.")
    store[RECUPERACION] = {
        "publica": base64.b64encode(publica_a_bytes(publica)).decode("ascii"),
        "huella": huella(publica),
    }
    _guardar_store(store)


def publica_recuperacion():
    entrada = _cargar_store().get(RECUPERACION)
    return bytes_a_publica(base64.b64decode(entrada["publica"])) if entrada else None


def huella_recuperacion() -> str:
    entrada = _cargar_store().get(RECUPERACION)
    return entrada["huella"] if entrada else ""


def cifrar_para(datos: bytes, destinatarios_: dict[str, object]) -> bytes:
    """Cifra con el sobre de recuperación del equipo, que es obligatorio."""
    recuperacion = publica_recuperacion()
    if recuperacion is None:
        raise CryptoError("Este equipo todavía no tiene clave de recuperación.")
    return cifrar(datos, destinatarios_, recuperacion=recuperacion)


def tiene_identidad(usuario: str) -> bool:
    return usuario.lower() in _cargar_store()


def _entrada(privada, password: str, huella_rec: str, pendiente: bool) -> dict:
    # La huella va autenticada junto a la privada: quien la cambie en el
    # archivo invalida la identidad.
    blob, sal = envolver_privada(privada, password, aad=huella_rec.encode("ascii"))
    return {
        "v": VERSION,
        "publica": base64.b64encode(publica_a_bytes(privada)).decode("ascii"),
        "privada": base64.b64encode(blob).decode("ascii"),
        "sal": base64.b64encode(sal).decode("ascii"),
        "n": _SCRYPT_N,
        "huella_rec": huella_rec,
        "pendiente_recuperacion": pendiente,
    }


def _guardar_entrada(usuario: str, entrada: dict) -> None:
    store = _cargar_store()
    store[usuario.lower()] = entrada
    _guardar_store(store)


def crear_identidad(usuario: str, password: str, *, pendiente: bool = False) -> None:
    """Genera el par de claves del usuario y guarda la privada bajo su contraseña."""
    _guardar_entrada(usuario, _entrada(generar_par(), password,
                                       huella_recuperacion(), pendiente))


def publica_de(usuario: str):
    entrada = _cargar_store().get(usuario.lower())
    if not entrada:
        return None
    return bytes_a_publica(base64.b64decode(entrada["publica"]))


def _abrir_entrada(entrada: dict, password: str):
    """Abre la privada y comprueba que la pública guardada sea la suya."""
    blob = base64.b64decode(entrada["privada"])
    sal = base64.b64decode(entrada["sal"])
    if entrada.get("v", 2) >= 3:
        privada = desenvolver_privada(blob, password, sal,
                                      aad=entrada["huella_rec"].encode("ascii"),
                                      n=entrada["n"])
    else:
        privada = desenvolver_privada(blob, password, sal, n=_SCRYPT_N_ANTERIOR)
    if publica_a_bytes(privada) != base64.b64decode(entrada["publica"]):
        raise IdentidadAlterada(
            "La clave pública guardada para esta cuenta no es la suya: "
            "el almacén de identidades fue modificado."
        )
    return privada


def cargar_privada(usuario: str, password: str):
    """
    Desenvuelve la clave privada con la contraseña. None si no se puede.

    :raises IdentidadAlterada: abre, pero la pública guardada es de otra clave.
    """
    entrada = _cargar_store().get(usuario.lower())
    if not entrada:
        return None
    try:
        return _abrir_entrada(entrada, password)
    except IdentidadAlterada:
        raise
    except Exception:
        return None


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
    previa = _cargar_store()[usuario.lower()]
    _guardar_entrada(usuario, _entrada(privada, nueva, huella_recuperacion(),
                                       previa.get("pendiente_recuperacion", False)))
    return True


def abrir_o_crear_identidad(usuario: str, password: str):
    """
    La clave privada de quien acaba de autenticarse: (privada, regenerada).

    Windows ya validó la contraseña. Si aun así no abre la privada, es que
    cambió por fuera de Custodia: se genera una identidad nueva, marcada a la
    espera de que el dueño del equipo le devuelva sus archivos con la USB.

    :raises IdentidadAlterada: la clave de recuperación del equipo no es la
        que esta identidad conoce.
    """
    store = _cargar_store()
    entrada = store.get(usuario.lower())
    if entrada is None:
        crear_identidad(usuario, password)
        return cargar_privada(usuario, password), False

    huella_equipo = huella_recuperacion()
    conocida = entrada.get("huella_rec", "")
    if conocida and conocida != huella_equipo:
        raise IdentidadAlterada(
            "La clave de recuperación de este equipo cambió desde que se creó "
            "esta identidad: el almacén de identidades fue modificado."
        )

    privada = cargar_privada(usuario, password)
    if privada is None:
        crear_identidad(usuario, password, pendiente=True)
        return cargar_privada(usuario, password), True

    if entrada.get("v", 2) < VERSION or not conocida:
        _guardar_entrada(usuario, _entrada(privada, password, huella_equipo,
                                           entrada.get("pendiente_recuperacion", False)))
    return privada, False


def pendiente_recuperacion(usuario: str) -> bool:
    entrada = _cargar_store().get(usuario.lower())
    return bool(entrada and entrada.get("pendiente_recuperacion"))


def marcar_recuperada(usuario: str) -> None:
    store = _cargar_store()
    store[usuario.lower()]["pendiente_recuperacion"] = False
    _guardar_store(store)


def fusionar_store(datos: dict) -> None:
    """Añade lo que falte, sin pisar nunca una identidad que ya existe."""
    store = _cargar_store()
    for clave, valor in datos.items():
        store.setdefault(clave, valor)
    _guardar_store(store)
