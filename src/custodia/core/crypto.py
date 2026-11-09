# -*- coding: utf-8 -*-
"""
Cifrado de archivos en reposo (RF-08, RNF-08).

Segunda capa de protección, independiente de la primera. Los permisos NTFS
impiden el acceso por los canales normales del sistema operativo; el cifrado
cubre el caso en que esos permisos dejan de aplicarse: si alguien extrae el
disco, lo monta desde otro equipo o arranca otro sistema operativo, las ACL
son solo metadatos que puede ignorar. El contenido cifrado sigue siendo
ilegible. Es el principio de confidencialidad que la propuesta plantea, y la
razón por la que las dos capas no son redundantes.

------------------------------------------------------------------------------
Algoritmo
------------------------------------------------------------------------------
AES-256 en modo GCM. GCM y no CBC porque además de cifrar **autentica**: si un
byte del archivo se altera en disco, el descifrado falla con una excepción en
lugar de devolver basura silenciosamente. Detectar la manipulación importa
tanto como impedir la lectura.

Cada archivo se cifra con un nonce aleatorio de 96 bits, distinto siempre. En
GCM, repetir un nonce con la misma clave rompe la seguridad del esquema por
completo, así que nunca se deriva ni se reutiliza: se genera con
`os.urandom` en cada escritura.

------------------------------------------------------------------------------
Gestión de la clave
------------------------------------------------------------------------------
La clave maestra son 32 bytes aleatorios generados una sola vez. El problema
clásico es dónde guardarla: escribirla en un archivo la deja expuesta, y
escribirla en el código fuente es peor.

Custodia la protege con **DPAPI** (Data Protection API), el servicio de cifrado
del propio Windows. `CryptProtectData` devuelve un blob que solo puede
descifrarse en esta máquina, porque la clave que lo protege deriva de secretos
que Windows guarda en la LSA y nunca expone. En disco queda un archivo
ilegible; la clave en claro solo existe en memoria mientras la aplicación corre.

Se usa el ámbito de máquina (`CRYPTPROTECT_LOCAL_MACHINE`) y no el de usuario,
porque las operaciones ocurren bajo identidades suplantadas distintas y todas
deben poder descifrar. Esto tiene una consecuencia honesta que conviene
documentar: **cualquier proceso que corra en esta máquina puede llamar a
`CryptUnprotectData` sobre ese blob.** Se mitiga con dos medidas —una ACL sobre
el archivo de clave que solo permite Administradores y SYSTEM, y una entropía
adicional propia de la aplicación que hay que conocer para descifrar— pero no
se elimina. El cifrado protege contra el acceso al disco fuera de este Windows,
no contra un atacante que ya ejecuta código con privilegios dentro de él.

------------------------------------------------------------------------------
Formato del archivo cifrado
------------------------------------------------------------------------------
    magia     8 bytes   b"CUSTODIA"
    version   1 byte    0x01
    tam_claro 8 bytes   tamaño del contenido original (uint64, little endian)
    nonce    12 bytes   aleatorio por archivo
    cuerpo    n bytes   AES-256-GCM (ciphertext + etiqueta de 16 bytes)

El tamaño original va en la cabecera para que la interfaz pueda mostrar el peso
real de un archivo sin descifrarlo entero.
"""
from __future__ import annotations

import os
import struct
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import ntsecuritycon as con
import win32crypt
import win32security
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from . import config
from .errors import CryptoError
from .impersonate import is_impersonating

MAGIA = b"CUSTODIA"
VERSION = 1
TAM_NONCE = 12
TAM_CABECERA = len(MAGIA) + 1 + 8 + TAM_NONCE   # 29 bytes
_CABECERA = struct.Struct("<8sBQ")               # magia, version, tam_claro

#: Entropía adicional que se mezcla en DPAPI. No es un secreto fuerte (está en
#: el código), pero obliga a que un atacante conozca esta aplicación en
#: concreto: no basta con llamar a CryptUnprotectData sobre el blob.
_ENTROPIA = b"Custodia/v1/clave-maestra"

#: Ámbito de máquina: el blob lo puede descifrar cualquier usuario de ESTE
#: equipo, que es lo que se necesita al operar bajo identidades suplantadas.
_CRYPTPROTECT_LOCAL_MACHINE = 0x4

_clave_cache: bytes | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Clave maestra
# ---------------------------------------------------------------------------

def _proteger_archivo_de_clave(ruta: Path) -> None:
    """
    Restringe el archivo de clave a Administradores y SYSTEM, sin herencia.

    Sin esto, el archivo heredaría los permisos de ProgramData, donde el grupo
    Usuarios tiene lectura, y el blob quedaría al alcance de cualquier cuenta
    de la máquina.
    """
    dacl = win32security.ACL()
    for sid_txt in ("S-1-5-32-544", "S-1-5-18"):   # Administradores, SYSTEM
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS, 0, con.FILE_ALL_ACCESS,
            win32security.ConvertStringSidToSid(sid_txt),
        )
    win32security.SetNamedSecurityInfo(
        str(ruta), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION
        | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
        None, None, dacl, None,
    )


def proteger_solo_admin(ruta: Path | str) -> None:
    """
    Restringe un archivo a Administradores y SYSTEM, sin herencia.

    Versión pública de la protección que usa la clave maestra, para que los
    demás secretos de la aplicación (segundo factor, registro de intentos)
    queden igual de resguardados con una sola línea.
    """
    _proteger_archivo_de_clave(Path(ruta))


def crear_clave_maestra(ruta: Path | None = None, *, forzar: bool = False) -> None:
    """
    Genera la clave maestra y la guarda protegida con DPAPI.

    Se llama una sola vez, desde el script de inicialización.

    :param forzar: regenerar aunque ya exista. **Destructivo**: todos los
        archivos cifrados con la clave anterior quedan irrecuperables.
    """
    ruta = Path(ruta or config.KEY_FILE)

    if ruta.exists() and not forzar:
        raise CryptoError(
            f"Ya existe una clave maestra en {ruta}. Regenerarla dejaría "
            "ilegibles todos los archivos ya cifrados; usa forzar=True solo si "
            "es lo que quieres."
        )

    ruta.parent.mkdir(parents=True, exist_ok=True)

    clave = os.urandom(32)   # AES-256
    ruta.write_bytes(_blob_dpapi(clave))
    _proteger_archivo_de_clave(ruta)

    # La copia en claro desaparece de nuestras variables al salir de la función.
    # Python no garantiza el borrado de la memoria, así que no se promete más
    # de lo que se puede cumplir.
    del clave


def _blob_dpapi(clave: bytes) -> bytes:
    """Protege la clave con DPAPI, con ámbito de máquina y la entropía propia."""
    return win32crypt.CryptProtectData(
        clave,
        "Custodia: clave maestra de cifrado",
        _ENTROPIA,
        None, None,
        _CRYPTPROTECT_LOCAL_MACHINE,
    )


def _escribir_protegido(ruta: Path, datos: bytes) -> None:
    """Escribe un archivo que tiene la ACL restrictiva antes de recibir datos."""
    ruta.touch()
    _proteger_archivo_de_clave(ruta)
    with open(ruta, "wb") as f:
        f.write(datos)
        f.flush()
        os.fsync(f.fileno())


def clave_disponible() -> bool:
    """True si la clave maestra está cargada en memoria."""
    with _lock:
        return _clave_cache is not None


def clave_para_respaldo() -> bytes:
    """
    La clave maestra en claro, para volver a cifrarla en un respaldo (C13).

    Solo debe llamarla `respaldo.py`, con la identidad de la aplicación.
    """
    return _clave_maestra()


def clave_abre(clave: bytes, blob: bytes) -> bool:
    """¿Esta clave descifra este archivo cifrado con la clave maestra (v1)?"""
    nonce = blob[_CABECERA.size:TAM_CABECERA]
    try:
        AESGCM(clave).decrypt(nonce, blob[TAM_CABECERA:], None)
    except (InvalidTag, ValueError):
        return False
    return True


def es_archivo_v1(cabecera: bytes) -> bool:
    """True si son los primeros bytes de un archivo cifrado con la clave maestra."""
    return esta_cifrado(cabecera) and cabecera[len(MAGIA)] == VERSION


def instalar_clave_maestra(clave: bytes) -> Path | None:
    """
    Sustituye la clave maestra por `clave` y deja de usar la anterior (C13).

    El reemplazo es atómico: el blob nuevo va a un temporal con la ACL ya
    aplicada y solo al final se renombra. Si algo falla, `master.key` queda como
    estaba. A disco solo llegan blobs DPAPI, nunca la clave en claro.

    :return: la copia del blob anterior, o None si no había ninguno.
    """
    global _clave_cache

    if len(clave) != 32:
        raise CryptoError("La clave restaurada no mide 32 bytes.")
    if is_impersonating():
        raise CryptoError("La clave maestra no se puede instalar bajo suplantación.")

    ruta = Path(config.KEY_FILE)
    temporal = ruta.with_name(f"{ruta.name}.{uuid.uuid4().hex}.tmp")
    copia: Path | None = None

    with _lock:
        try:
            ruta.parent.mkdir(parents=True, exist_ok=True)
            _escribir_protegido(temporal, _blob_dpapi(clave))

            anterior = _leer_blob_anterior(ruta)
            if anterior is not None:
                marca = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
                copia = ruta.with_name(f"{ruta.name}.anterior-{marca}")
                _escribir_protegido(copia, anterior)

            os.replace(temporal, ruta)
        except Exception as exc:
            for sobrante in (temporal, copia):
                if sobrante is not None:
                    sobrante.unlink(missing_ok=True)
            raise CryptoError(
                "No se pudo guardar la clave maestra. La clave anterior no se "
                "modificó."
            ) from exc

        # Sin esto, la aplicación seguiría cifrando con la clave reemplazada
        # hasta el próximo arranque.
        _clave_cache = clave

    return copia


def _leer_blob_anterior(ruta: Path) -> bytes | None:
    """Lee el blob que se va a reemplazar; uno ilegible no impide recuperar."""
    try:
        return ruta.read_bytes()
    except OSError:
        return None


def purgar_copias_anteriores(dias: int) -> int:
    """Borra las copias de claves anteriores con más de `dias` días."""
    ruta = Path(config.KEY_FILE)
    limite = time.time() - dias * 86400
    borradas = 0
    for copia in ruta.parent.glob(f"{ruta.name}.anterior-*"):
        try:
            if copia.stat().st_mtime < limite:
                copia.unlink()
                borradas += 1
        except OSError:
            continue
    return borradas


def precargar_clave() -> None:
    """
    Carga la clave maestra en memoria. **Llamar al arrancar la aplicación.**

    ------------------------------------------------------------------------
    Por qué existe esta función
    ------------------------------------------------------------------------
    El archivo de clave tiene una ACL que solo permite Administradores y
    SYSTEM. Pero las operaciones sobre archivos ocurren dentro de un bloque de
    suplantación, donde el hilo es un usuario normal: si la clave se leyera
    ahí, Windows denegaría el acceso.

    Podría parecer que la solución es aflojar esa ACL, pero sería un error de
    diseño. La clave maestra **no es un recurso del usuario**: es un secreto de
    la aplicación. Si su acceso dependiera de los permisos del usuario, el
    modelo de seguridad se volvería incoherente —alguien con permiso NTFS de
    lectura sobre un archivo no podría descifrarlo— y la ACL del archivo de
    clave se convertiría en un segundo sistema de permisos paralelo al de NTFS.

    Quien decide si un usuario puede leer un archivo es NTFS, y solo NTFS. Una
    vez que NTFS dijo que sí, descifrar es un detalle de implementación que la
    aplicación resuelve con su propio secreto.

    Por eso la clave se carga una vez al arrancar, mientras la aplicación
    todavía corre con su identidad privilegiada, y a partir de ahí vive en
    memoria. Dentro de la suplantación solo se lee el caché; nunca el disco.
    """
    _clave_maestra()


def _clave_maestra() -> bytes:
    """
    Devuelve la clave maestra, cargándola de disco la primera vez.

    El caché evita una llamada a DPAPI por cada archivo. La clave vive solo en
    memoria del proceso; nunca se escribe.
    """
    global _clave_cache

    with _lock:
        if _clave_cache is not None:
            return _clave_cache

        # Guardia de diagnóstico: sin esto, el fallo se manifiesta como un
        # "Acceso denegado" a una ruta que no tiene nada que ver con lo que el
        # usuario estaba haciendo, y cuesta mucho relacionarlo con la causa.
        if is_impersonating():
            raise CryptoError(
                "La clave maestra no estaba cargada y se intentó leer dentro de "
                "una suplantación, donde el usuario no tiene permiso sobre el "
                "archivo de clave. Llama a crypto.precargar_clave() al arrancar "
                "la aplicación, antes de suplantar a nadie."
            )

        ruta = Path(config.KEY_FILE)
        if not ruta.exists():
            raise CryptoError(
                f"No existe la clave maestra en {ruta}. Ejecuta primero "
                "scripts\\bootstrap.py."
            )

        try:
            _, clave = win32crypt.CryptUnprotectData(
                ruta.read_bytes(), _ENTROPIA, None, None, 0
            )
        except Exception as exc:
            raise CryptoError(
                "No se pudo descifrar la clave maestra. Suele significar que el "
                "archivo fue copiado desde otra máquina: DPAPI la protege con "
                "secretos locales, así que el blob no es portable."
            ) from exc

        if len(clave) != 32:
            raise CryptoError("La clave maestra no mide 32 bytes; está corrupta")

        _clave_cache = clave
        return clave


def olvidar_clave() -> None:
    """Vacía el caché en memoria. Útil en pruebas y al cerrar la aplicación."""
    global _clave_cache
    with _lock:
        _clave_cache = None


# ---------------------------------------------------------------------------
# Cifrado y descifrado
# ---------------------------------------------------------------------------

def cifrar(datos: bytes) -> bytes:
    """Cifra contenido y devuelve el archivo completo, con su cabecera."""
    if not config.CIFRADO_ACTIVO:
        return datos

    nonce = os.urandom(TAM_NONCE)
    cuerpo = AESGCM(_clave_maestra()).encrypt(nonce, datos, None)
    return _CABECERA.pack(MAGIA, VERSION, len(datos)) + nonce + cuerpo


def descifrar(blob: bytes) -> bytes:
    """
    Descifra el contenido de un archivo de Custodia.

    Si el archivo no lleva la cabecera se devuelve tal cual: permite leer
    archivos que existían antes de activar el cifrado, o colocados a mano en la
    carpeta, sin que la aplicación se rompa.
    """
    if not esta_cifrado(blob):
        return blob

    _, version, tam_claro = _CABECERA.unpack_from(blob, 0)
    if version != VERSION:
        raise CryptoError(f"Versión de formato desconocida: {version}")

    nonce = blob[_CABECERA.size:TAM_CABECERA]
    cuerpo = blob[TAM_CABECERA:]

    try:
        datos = AESGCM(_clave_maestra()).decrypt(nonce, cuerpo, None)
    except InvalidTag as exc:
        raise CryptoError(
            "El archivo no se pudo descifrar: la etiqueta de autenticación no "
            "coincide. El contenido fue alterado en disco o se cifró con otra "
            "clave maestra."
        ) from exc

    if len(datos) != tam_claro:
        raise CryptoError("El tamaño descifrado no coincide con la cabecera")

    return datos


def esta_cifrado(blob: bytes) -> bool:
    """True si el contenido empieza con la cabecera de Custodia."""
    return len(blob) >= TAM_CABECERA and blob[:len(MAGIA)] == MAGIA


def tamano_original(ruta: Path) -> int | None:
    """
    Lee de la cabecera el tamaño del contenido sin descifrar el archivo.

    Solo lee los primeros 29 bytes, así que sirve para mostrar el peso real en
    un listado sin el coste de descifrar. Devuelve None si el archivo no está
    cifrado o no se puede leer.
    """
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(TAM_CABECERA)
    except OSError:
        return None

    if len(cabecera) < TAM_CABECERA or cabecera[:len(MAGIA)] != MAGIA:
        return None

    _, _, tam = _CABECERA.unpack_from(cabecera, 0)
    return tam
