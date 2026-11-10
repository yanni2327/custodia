# -*- coding: utf-8 -*-
"""
Respaldo y recuperación de la clave maestra (control C13, riesgo R9).

El blob DPAPI de `master.key` solo se abre en este equipo, así que no sirve como
respaldo. Aquí la clave se descifra con la identidad de la aplicación y se
vuelve a cifrar con una contraseña de recuperación que elige el administrador.

------------------------------------------------------------------------------
Formato del archivo de respaldo (88 bytes exactos)
------------------------------------------------------------------------------
    magia      8 bytes   b"CUSTKEYB"
    version    1 byte    0x01
    log2_n     1 byte    coste de scrypt
    r          1 byte
    p          1 byte
    sal       16 bytes   aleatoria
    nonce     12 bytes   aleatorio
    cifrado   48 bytes   clave (32) + etiqueta GCM (16)

Toda la cabecera entra como dato autenticado de GCM: alterar un solo byte,
incluidos los parámetros de scrypt, hace fallar el descifrado.

GCM no distingue una contraseña incorrecta de un archivo alterado, porque en
ambos casos solo falla la etiqueta. Por eso el error es uno solo y lo dice así.

Límite honesto: Python no permite borrar de la memoria la clave ni la
contraseña. Aquí no se escriben en disco ni en la bitácora; más no se promete.
"""
from __future__ import annotations

import json
import os
import struct
import unicodedata
import uuid
from itertools import islice
from pathlib import Path
from typing import Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from . import boveda, config, crypto
from .errors import CryptoError, RespaldoError

MAGIA = b"CUSTKEYB"
MAGIA_IDENTIDADES = b"CUSTIDEN"
VERSION = 1
EXTENSION = ".custodiakey"
SUFIJO_IDENTIDADES = ".identidades"
LONGITUD_MINIMA = 12

_CABECERA = struct.Struct("<8sBBBB16s12s")   # magia, versión, log2_n, r, p, sal, nonce
TAM_ARCHIVO = _CABECERA.size + 32 + 16        # 88 bytes

# Este archivo sale del equipo y se puede atacar sin conexión: por eso el coste
# es mayor que el de boveda.py (2**15). Unos 0,7 s en un equipo de escritorio.
_LOG2_N = 18
_R = 8
_P = 1

# Topes al leer: un archivo manipulado no debe poder reservar memoria sin límite
# antes de que falle la etiqueta. Como máximo, 1 GB.
_LOG2_N_RANGO = range(15, 21)
_R_RANGO = range(1, 9)
_P_RANGO = range(1, 3)

#: Archivos del almacén que se prueban, como máximo, al verificar una clave.
MAX_ARCHIVOS_A_PROBAR = 20


def _no_descifrable() -> RespaldoError:
    # Una instancia nueva por fallo: una compartida acumularía en su traceback
    # referencias a las variables locales con la contraseña.
    return RespaldoError(
        "Contraseña incorrecta o archivo alterado. No se modificó nada.",
        "contraseña incorrecta o archivo alterado",
    )


def _no_reconocido() -> RespaldoError:
    return RespaldoError(
        "Ese archivo no es un respaldo de la clave de Custodia. No se modificó nada.",
        "formato no reconocido",
    )


class Restauracion:
    """
    Una clave ya descifrada y verificada, pendiente de confirmación.

    Es opaca a propósito: su `repr` no muestra la clave, así que un registro o
    un mensaje de depuración no puede filtrarla por accidente.
    """

    __slots__ = ("_clave", "_identidades", "verificada", "reemplaza")

    def __init__(self, clave: bytes, verificada: bool, reemplaza: bool,
                 identidades: dict | None = None) -> None:
        self._clave = clave
        self._identidades = identidades
        #: True si la clave abrió un archivo del almacén; False si no había
        #: ninguno con el que comprobarla.
        self.verificada = verificada
        #: True si ya hay un `master.key` que se va a sustituir.
        self.reemplaza = reemplaza

    def __repr__(self) -> str:
        return (f"Restauracion(verificada={self.verificada}, "
                f"reemplaza={self.reemplaza})")


def regla_contrasena(password: str) -> str | None:
    """Devuelve el motivo por el que la contraseña no vale, o None si vale."""
    if len(password) < LONGITUD_MINIMA:
        return (f"La contraseña de recuperación debe tener al menos "
                f"{LONGITUD_MINIMA} caracteres.")
    return None


def _derivar(password: str, sal: bytes, log2_n: int, r: int, p: int) -> bytes:
    # NFC: la misma contraseña escrita en otro teclado debe dar los mismos bytes.
    secreto = unicodedata.normalize("NFC", password).encode("utf-8")
    return Scrypt(salt=sal, length=32, n=2 ** log2_n, r=r, p=p).derive(secreto)


def sellar(clave: bytes, password: str) -> bytes:
    """Cifra la clave maestra con la contraseña y devuelve el archivo completo."""
    sal = os.urandom(16)
    nonce = os.urandom(12)
    cabecera = _CABECERA.pack(MAGIA, VERSION, _LOG2_N, _R, _P, sal, nonce)
    kek = _derivar(password, sal, _LOG2_N, _R, _P)
    return cabecera + AESGCM(kek).encrypt(nonce, clave, cabecera)


def abrir(datos: bytes, password: str) -> bytes:
    """
    Descifra un archivo de respaldo y devuelve la clave maestra.

    :raises RespaldoError: formato no reconocido, contraseña incorrecta o
        archivo alterado.
    """
    if len(datos) != TAM_ARCHIVO:
        raise _no_reconocido()

    cabecera = datos[:_CABECERA.size]
    magia, version, log2_n, r, p, sal, nonce = _CABECERA.unpack(cabecera)
    if magia != MAGIA or version != VERSION:
        raise _no_reconocido()
    if log2_n not in _LOG2_N_RANGO or r not in _R_RANGO or p not in _P_RANGO:
        # Parámetros fuera de lo que este programa escribe: manipulación.
        raise _no_descifrable()

    kek = _derivar(password, sal, log2_n, r, p)
    try:
        clave = AESGCM(kek).decrypt(nonce, datos[_CABECERA.size:], cabecera)
    except InvalidTag:
        raise _no_descifrable() from None

    if len(clave) != 32:
        raise _no_descifrable()
    return clave


def sellar_datos(magia: bytes, datos: bytes, password: str) -> bytes:
    """Como `sellar`, para contenidos de cualquier tamaño y con otra magia."""
    sal = os.urandom(16)
    nonce = os.urandom(12)
    cabecera = _CABECERA.pack(magia, VERSION, _LOG2_N, _R, _P, sal, nonce)
    kek = _derivar(password, sal, _LOG2_N, _R, _P)
    return cabecera + AESGCM(kek).encrypt(nonce, datos, cabecera)


def abrir_datos(magia: bytes, datos: bytes, password: str) -> bytes:
    """
    Descifra lo que produjo `sellar_datos`.

    :raises RespaldoError: formato no reconocido, contraseña incorrecta o
        archivo alterado.
    """
    if len(datos) <= _CABECERA.size:
        raise _no_reconocido()
    cabecera = datos[:_CABECERA.size]
    leida, version, log2_n, r, p, sal, nonce = _CABECERA.unpack(cabecera)
    if leida != magia or version != VERSION:
        raise _no_reconocido()
    if log2_n not in _LOG2_N_RANGO or r not in _R_RANGO or p not in _P_RANGO:
        raise _no_descifrable()
    kek = _derivar(password, sal, log2_n, r, p)
    try:
        return AESGCM(kek).decrypt(nonce, datos[_CABECERA.size:], cabecera)
    except InvalidTag:
        raise _no_descifrable() from None


def _archivos_v1() -> Iterator[Path]:
    """Archivos del almacén cifrados con la clave maestra y legibles."""
    for carpeta, _, nombres in os.walk(config.STORAGE_ROOT):
        for nombre in nombres:
            ruta = Path(carpeta) / nombre
            try:
                with open(ruta, "rb") as f:
                    cabecera = f.read(crypto.TAM_CABECERA)
            except OSError:
                continue
            if crypto.es_archivo_v1(cabecera):
                yield ruta


def clave_perdida() -> bool:
    """
    ¿Falta `master.key` en un almacén que ya tiene archivos cifrados?

    En ese caso no hay que generar otra clave, porque todo lo escrito con ella
    se perdería al restaurar el respaldo.
    """
    if Path(config.KEY_FILE).exists():
        return False
    return next(_archivos_v1(), None) is not None


def verificar_contra_almacen(clave: bytes) -> bool:
    """
    Comprueba que la clave abre algún archivo del almacén.

    Basta con que abra uno: un solo archivo dañado no debe impedir recuperar
    todos los demás.

    :return: True si abrió uno; False si no había ninguno con el que probar.
    :raises RespaldoError: ninguno de los archivos probados se abrió.
    """
    probados = 0
    for ruta in islice(_archivos_v1(), MAX_ARCHIVOS_A_PROBAR):
        try:
            blob = ruta.read_bytes()
        except OSError:
            continue
        probados += 1
        if crypto.clave_abre(clave, blob):
            return True

    if probados:
        raise RespaldoError(
            "Esta clave no abre los archivos del almacén, así que el respaldo "
            "no corresponde a estos datos. No se modificó nada.",
            "la clave no abre los archivos del almacén",
        )
    return False


def validar_destino(destino: Path) -> None:
    """El respaldo no debe quedar junto a lo que protege."""
    resuelto = destino.resolve()
    prohibidas = (Path(config.STORAGE_ROOT).resolve(),
                  Path(config.KEY_FILE).resolve().parent)
    if any(resuelto.is_relative_to(carpeta) for carpeta in prohibidas):
        raise RespaldoError(
            "Elige otro lugar: el respaldo no puede guardarse en el almacén ni "
            "junto a la clave maestra. Lo ideal es una USB.",
            "destino no permitido",
        )


def escribir_verificado(destino: Path, contenido: bytes) -> None:
    """
    Escritura atómica y relectura, para detectar ahora, y no el día que haga
    falta, una USB que no guardó bien los datos.
    """
    temporal = destino.with_name(f"{destino.name}.{uuid.uuid4().hex}.tmp")
    try:
        with open(temporal, "wb") as f:
            f.write(contenido)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, destino)
        guardado = destino.read_bytes()
    except OSError as exc:
        temporal.unlink(missing_ok=True)
        raise RespaldoError(
            "No se pudo escribir el respaldo en ese lugar. Comprueba que la "
            "unidad esté conectada y tenga permisos de escritura.",
            "no se pudo escribir el destino",
        ) from exc

    if guardado != contenido:
        raise RespaldoError(
            "El respaldo se escribió con errores: lo guardado no coincide. "
            "Prueba con otra unidad.",
            "el destino no guardó bien el archivo",
        )


def _ruta_identidades(respaldo_clave: Path) -> Path:
    return respaldo_clave.with_name(respaldo_clave.name + SUFIJO_IDENTIDADES)


def exportar(password: str, destino: Path | str) -> None:
    """
    Escribe el respaldo de la clave maestra en `destino`.

    Si hay cifrado por usuario, junto a él va una copia de las identidades:
    sin `identidades.json`, los archivos v3 serían irrecuperables.
    """
    error = regla_contrasena(password)
    if error:
        raise RespaldoError(error, "contraseña de recuperación demasiado corta")

    destino = Path(destino)
    validar_destino(destino)

    try:
        clave = crypto.clave_para_respaldo()
    except CryptoError:
        raise RespaldoError(
            "La clave maestra de este equipo no está disponible, así que no se "
            "puede respaldar. Restaura un respaldo anterior.",
            "clave maestra no disponible",
        ) from None
    escribir_verificado(destino, sellar(clave, password))

    identidades = Path(config.BOVEDA_FILE)
    if identidades.exists():
        escribir_verificado(_ruta_identidades(destino), sellar_datos(
            MAGIA_IDENTIDADES, identidades.read_bytes(), password))


def preparar(origen: Path | str, password: str) -> Restauracion:
    """
    Descifra un respaldo y lo verifica, **sin escribir nada**.

    La instalación es un paso aparte (`aplicar`) porque antes hay que pedirle
    al administrador la confirmación explícita.
    """
    ruta = Path(origen)
    try:
        if ruta.stat().st_size != TAM_ARCHIVO:
            raise _no_reconocido()
        datos = ruta.read_bytes()
    except OSError as exc:
        raise RespaldoError(
            "No se pudo leer el archivo de respaldo.",
            "no se pudo leer el archivo",
        ) from exc

    clave = abrir(datos, password)
    verificada = verificar_contra_almacen(clave)

    identidades = None
    copia = _ruta_identidades(ruta)
    if copia.exists():
        contenido = abrir_datos(MAGIA_IDENTIDADES, copia.read_bytes(), password)
        try:
            identidades = json.loads(contenido)
        except ValueError:
            raise _no_descifrable() from None

    return Restauracion(clave, verificada, Path(config.KEY_FILE).exists(), identidades)


def aplicar(restauracion: Restauracion) -> Path | None:
    """
    Instala la clave preparada. Devuelve la copia de la anterior, si la hubo.

    Las identidades solo se añaden si faltan: las que hay pueden ser más nuevas
    que el respaldo.
    """
    copia = crypto.instalar_clave_maestra(restauracion._clave)
    if restauracion._identidades:
        boveda.fusionar_store(restauracion._identidades)
    return copia
