# -*- coding: utf-8 -*-
"""
Operaciones sobre el sistema de archivos real.

Comparación con el proyecto anterior: allí ``crear_archivo`` era un INSERT en
una tabla ``nodes`` con el contenido en una columna LONGTEXT. Aquí es un
``open(..., "wb")``. El archivo existe en el disco, se puede abrir con el
Bloc de notas, y su tamaño es de bytes de verdad.

Contrato de este módulo, sin excepciones:

1. Toda función recibe rutas ya validadas por :mod:`jail`, nunca cadenas crudas.
2. Toda función se ejecuta con :func:`impersonate.assert_impersonating` activo.
   Sin suplantación, la operación correría con los privilegios administrativos
   del servicio y saltaría todo el control de acceso.
3. Los "no" del kernel se traducen a :class:`PermissionDenied`. En ningún punto
   de este archivo hay un ``if`` que decida si el usuario tiene permiso: esa
   decisión es del sistema operativo.
"""
from __future__ import annotations

import functools
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import acl, audit, config, crypto
from .errors import AlreadyExists, CustodiaError, FileTooLarge, NotFound
from .impersonate import assert_impersonating, current_identity, translate_denials
from .jail import to_virtual, validar_nombre


@dataclass
class NodoInfo:
    """Metadatos de un archivo o carpeta, listos para enviar a la interfaz."""

    nombre: str
    ruta: str              # ruta virtual, nunca la física de Windows
    es_carpeta: bool
    tamano: int            # bytes que ocupa en disco (incluye cabecera y cifrado)
    creado: str            # ISO 8601
    modificado: str
    propietario: str | None = None
    tamano_claro: int | None = None   # tamaño del contenido original
    cifrado: bool = False


def _auditado(accion: str):
    """
    Registra en la bitácora cada intento, salga bien o mal (RF-05).

    Tres decisiones que vale la pena justificar:

    **El usuario se toma de la identidad efectiva del hilo**, no de un
    parámetro. Dentro del bloque de suplantación, `current_identity()` devuelve
    el usuario que Windows tiene por activo, que es exactamente el que el
    kernel usó para autorizar o denegar. Si se pasara como argumento, un error
    de programación podría registrar a una persona distinta de la que realmente
    ejecutó la operación, y la bitácora dejaría de ser evidencia.

    **Se anota el intento, no solo el éxito.** Lo que el RF-05 hace útil es
    poder responder quién trató de acceder a algo que no le correspondía; un
    registro que solo guarda lo que salió bien no contesta esa pregunta.

    **Se guarda la ruta virtual**, no la física de Windows. La bitácora la va a
    leer una persona en la interfaz, y filtrar rutas absolutas del servidor no
    le aporta nada.
    """
    def decorador(fn):
        @functools.wraps(fn)
        def envoltura(ruta, *args, **kwargs):
            usuario = current_identity()
            try:
                ruta_registrada = to_virtual(Path(ruta))
            except Exception:
                # `to_virtual` resuelve la ruta, y resolver toca el disco: si
                # el usuario no tiene permiso, falla. No se deja que eso impida
                # registrar el evento, que es justamente el más interesante.
                ruta_registrada = Path(ruta).name

            try:
                resultado = fn(ruta, *args, **kwargs)
            except CustodiaError as exc:
                audit.registrar(usuario, accion, ruta_registrada, exito=False,
                                detalle=f"{type(exc).__name__}: {exc}")
                raise

            audit.registrar(usuario, accion, ruta_registrada, exito=True)
            return resultado
        return envoltura
    return decorador


def _existe(ruta: Path) -> bool:
    """
    ``ruta.exists()`` con la denegación traducida.

    Todas las funciones de este módulo corren bajo suplantación, así que
    cualquier consulta al disco —incluso averiguar si un archivo existe— pasa
    por el control de acceso. Si el usuario no puede ni hacer ``stat``, Python
    lanza ``PermissionError`` y sin esta traducción escaparía en crudo hacia la
    interfaz, saltándose las excepciones del dominio.

    Se responde denegado y no "no existe" a propósito: el archivo está ahí, y
    mentir sobre su existencia daría a la interfaz una razón equivocada para un
    fallo que en realidad es de permisos.
    """
    with translate_denials(ruta.name):
        return ruta.exists()


def _es_carpeta(ruta: Path) -> bool:
    """``ruta.is_dir()`` con la denegación traducida. Ver :func:`_existe`."""
    with translate_denials(ruta.name):
        return ruta.is_dir()


def _a_info(ruta: Path, *, con_propietario: bool = False,
            con_tamano_claro: bool = False) -> NodoInfo:
    # También traducido: `_a_info` se llama tanto dentro como fuera de un
    # bloque `translate_denials`, y leer los metadatos de un elemento sobre el
    # que el usuario no tiene permiso es un caso normal, no un error interno.
    with translate_denials(ruta.name):
        st = ruta.stat()
        es_carpeta = ruta.is_dir()

    prop = None
    if con_propietario:
        try:
            prop = acl.propietario(ruta)
        except Exception:
            prop = None  # que un permiso ausente no rompa el listado entero

    # El tamaño original vive en la cabecera del archivo cifrado, así que
    # obtenerlo cuesta leer 29 bytes. Se hace solo cuando se piden los detalles
    # de un elemento concreto, no en cada fila de un listado.
    tam_claro = None
    if con_tamano_claro and not es_carpeta:
        tam_claro = crypto.tamano_original(ruta)

    return NodoInfo(
        nombre=ruta.name,
        ruta=to_virtual(ruta),
        es_carpeta=es_carpeta,
        tamano=0 if es_carpeta else st.st_size,
        creado=datetime.fromtimestamp(st.st_ctime, timezone.utc).isoformat(),
        modificado=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        propietario=prop,
        tamano_claro=tam_claro,
        cifrado=tam_claro is not None,
    )


@_auditado("listar")
def listar(ruta: Path, *, con_propietario: bool = False) -> list[NodoInfo]:
    """
    Lista el contenido de una carpeta.

    Si el usuario no tiene permiso de lectura sobre la carpeta, el propio
    ``os.scandir`` falla con acceso denegado. No hace falta comprobar nada antes.
    """
    assert_impersonating()

    if not _existe(ruta):
        raise NotFound(f"No existe: {ruta.name}")
    if not _es_carpeta(ruta):
        raise NotFound(f"'{ruta.name}' no es una carpeta")

    salida = []
    with translate_denials(ruta.name):
        with os.scandir(ruta) as it:
            for entrada in it:
                try:
                    # Se pide también el tamaño original: es lo que hace que
                    # la columna "Cifrado" y el candado del icono tengan algo
                    # que mostrar. Cuesta leer 29 bytes por archivo, que es el
                    # precio de que la garantía se vea en el listado y no solo
                    # al abrir los detalles de un elemento.
                    salida.append(_a_info(Path(entrada.path),
                                          con_propietario=con_propietario,
                                          con_tamano_claro=True))
                except PermissionError:
                    # El usuario ve que el elemento existe pero no puede leer sus
                    # metadatos. Es el comportamiento del Explorador de Windows.
                    continue

    return sorted(salida, key=lambda n: (not n.es_carpeta, n.nombre.lower()))


@_auditado("crear_carpeta")
def crear_carpeta(ruta: Path) -> NodoInfo:
    """Crea una carpeta real en el disco."""
    assert_impersonating()
    validar_nombre(ruta.name)

    if _existe(ruta):
        raise AlreadyExists(f"Ya existe '{ruta.name}'")

    with translate_denials(ruta.name):
        ruta.mkdir(parents=False)

    return _a_info(ruta)


@_auditado("escribir")
def escribir(ruta: Path, datos: bytes, *, sobrescribir: bool = False,
             cifrar: bool = True) -> NodoInfo:
    """
    Crea o sobrescribe un archivo, cifrando el contenido antes de tocar el disco.

    Binario y no texto a propósito: el modelo anterior guardaba el contenido en
    una columna de texto, así que no admitía imágenes, PDF ni ejecutables. Este
    acepta cualquier archivo.

    La escritura es **atómica** (RNF-05): el contenido va primero a un archivo
    temporal en la misma carpeta y solo al final se renombra sobre el destino
    con ``os.replace``, que en el mismo volumen es una operación atómica del
    sistema de archivos. Consecuencias:

    - Si el usuario no tiene permiso, falla al crear el temporal y en disco no
      queda absolutamente nada.
    - Si el proceso muere a media escritura, el destino conserva su versión
      anterior intacta y el temporal se borra en el ``finally``.
    - Nunca existe un archivo a medio escribir con el nombre definitivo.
    """
    assert_impersonating()
    validar_nombre(ruta.name)

    if len(datos) > config.MAX_FILE_BYTES:
        raise FileTooLarge(
            f"El archivo supera el límite de {config.MAX_FILE_BYTES // (1024*1024)} MB"
        )

    existia = _existe(ruta)
    if existia and not sobrescribir:
        raise AlreadyExists(f"Ya existe '{ruta.name}'")

    # `cifrar=False` cuando el contenido ya viene cifrado por quien llama (el
    # cifrado por usuario envuelve en la capa de sesión, con la identidad del
    # usuario). En el modo normal, aquí se aplica la clave maestra.
    contenido = crypto.cifrar(datos) if cifrar else datos

    # Al sobrescribir, os.replace sustituye el archivo entero, incluida su DACL.
    # Sin este rescate, guardar un archivo borraría los permisos que alguien le
    # hubiera puesto. Se conserva y se reaplica después.
    dacl_previa = None
    if existia:
        try:
            dacl_previa = [
                (e.principal, e.mascara, e.permitir, e.hereda_a_hijos)
                for e in acl.leer_permisos(ruta) if not e.heredado
            ]
        except Exception:
            dacl_previa = None

    temporal = ruta.parent / f".{ruta.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        with translate_denials(ruta.name):
            with open(temporal, "xb") as f:
                f.write(contenido)
                f.flush()
                os.fsync(f.fileno())   # que los bytes lleguen al disco, no al caché
            os.replace(temporal, ruta)
    finally:
        # Si algo falló, no dejamos basura suelta en la carpeta del usuario.
        try:
            temporal.unlink(missing_ok=True)
        except OSError:
            pass

    if dacl_previa:
        try:
            acl.establecer_permisos(ruta, dacl_previa)
        except Exception:
            # Sin permiso para reescribir la DACL. El archivo queda con los
            # permisos heredados de la carpeta, que es el comportamiento seguro.
            pass

    return _a_info(ruta)


@_auditado("leer")
def leer(ruta: Path, *, descifrar: bool = True) -> bytes:
    """
    Lee un archivo y devuelve su contenido descifrado.

    Orden importante: primero Windows decide si el usuario puede abrir el
    archivo, y solo si lo autoriza se descifra. El cifrado nunca sustituye al
    control de acceso, lo complementa.

    `descifrar=False` devuelve el contenido en bruto: lo usa el cifrado por
    usuario, que descifra en la capa de sesión con la clave privada del usuario.
    """
    assert_impersonating()

    if not _existe(ruta):
        raise NotFound(f"No existe: {ruta.name}")
    if _es_carpeta(ruta):
        raise NotFound(f"'{ruta.name}' es una carpeta, no un archivo")

    with translate_denials(ruta.name):
        tamano = ruta.stat().st_size
    if tamano > config.MAX_FILE_BYTES:
        raise FileTooLarge(
            f"El archivo pesa {tamano // (1024*1024)} MB y supera el límite de lectura"
        )

    with translate_denials(ruta.name):
        blob = ruta.read_bytes()

    return crypto.descifrar(blob) if descifrar else blob


@_auditado("eliminar")
def eliminar(ruta: Path, *, recursivo: bool = False) -> None:
    """Elimina un archivo o una carpeta."""
    assert_impersonating()

    if not _existe(ruta):
        raise NotFound(f"No existe: {ruta.name}")

    if ruta.resolve() == config.STORAGE_ROOT.resolve():
        raise NotFound("No se puede eliminar la raíz del sistema de archivos")

    with translate_denials(ruta.name):
        if _es_carpeta(ruta):
            if recursivo:
                # Si el usuario carece de permiso sobre algún descendiente,
                # rmtree falla a medio camino. Es el comportamiento correcto:
                # borrar parcialmente y reportar éxito sería peor.
                shutil.rmtree(ruta)
            else:
                ruta.rmdir()   # falla si no está vacía
        else:
            ruta.unlink()


@_auditado("renombrar")
def renombrar(ruta: Path, nuevo_nombre: str) -> NodoInfo:
    """Cambia el nombre de un archivo o carpeta dentro de su misma carpeta."""
    assert_impersonating()
    validar_nombre(nuevo_nombre)

    if not _existe(ruta):
        raise NotFound(f"No existe: {ruta.name}")

    destino = ruta.parent / nuevo_nombre
    if _existe(destino):
        raise AlreadyExists(f"Ya existe '{nuevo_nombre}'")

    with translate_denials(ruta.name):
        ruta.rename(destino)

    return _a_info(destino)


@_auditado("mover")
def mover(origen: Path, destino_carpeta: Path) -> NodoInfo:
    """Mueve un elemento a otra carpeta. Ambas rutas ya validadas por jail."""
    assert_impersonating()

    if not _existe(origen):
        raise NotFound(f"No existe: {origen.name}")
    if not _es_carpeta(destino_carpeta):
        raise NotFound(f"'{destino_carpeta.name}' no es una carpeta")

    destino = destino_carpeta / origen.name
    if _existe(destino):
        raise AlreadyExists(f"Ya existe '{origen.name}' en el destino")

    with translate_denials(origen.name):
        shutil.move(str(origen), str(destino))

    return _a_info(destino)


@_auditado("copiar")
def copiar(origen: Path, destino_carpeta: Path) -> NodoInfo:
    """
    Copia un elemento a otra carpeta.

    Detalle que importa: la copia **no** conserva la DACL del original. Hereda
    la de la carpeta destino, que es el comportamiento de Windows y el correcto
    aquí. Copiar un archivo confidencial a una carpeta pública debe hacerlo
    público, no propagar el permiso restringido a un sitio donde nadie lo espera.
    """
    assert_impersonating()

    if not _existe(origen):
        raise NotFound(f"No existe: {origen.name}")

    destino = destino_carpeta / origen.name
    if _existe(destino):
        raise AlreadyExists(f"Ya existe '{origen.name}' en el destino")

    with translate_denials(origen.name):
        if _es_carpeta(origen):
            shutil.copytree(origen, destino)
        else:
            shutil.copy2(origen, destino)

    return _a_info(destino)


def info(ruta: Path) -> NodoInfo:
    """Metadatos de un solo elemento, incluido el propietario."""
    assert_impersonating()
    if not _existe(ruta):
        raise NotFound(f"No existe: {ruta.name}")
    with translate_denials(ruta.name):
        return _a_info(ruta, con_propietario=True, con_tamano_claro=True)


def buscar(raiz: Path, patron: str, *, limite: int = 200) -> list[NodoInfo]:
    """
    Busca por nombre bajo una carpeta.

    Las carpetas sin permiso se saltan en silencio: el usuario no debe poder
    deducir qué existe donde no puede entrar. Un buscador que dijera "acceso
    denegado en X" filtraría la estructura del árbol.
    """
    assert_impersonating()
    patron = patron.lower().strip()
    if not patron:
        return []

    resultados: list[NodoInfo] = []
    for actual, dirs, archivos in os.walk(raiz, onerror=lambda e: None):
        for nombre in list(dirs) + archivos:
            if patron in nombre.lower():
                try:
                    resultados.append(_a_info(Path(actual) / nombre))
                except OSError:
                    continue
                if len(resultados) >= limite:
                    return resultados
    return resultados
