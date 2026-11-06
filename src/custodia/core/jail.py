# -*- coding: utf-8 -*-
"""
Confinamiento de rutas.

En cuanto los archivos son reales, un nombre deja de ser un dato inocente.
``..\\..\\Windows\\System32`` es una ruta perfectamente válida para el sistema
operativo. Este módulo garantiza que toda ruta que la aplicación toque quede
dentro de ``config.STORAGE_ROOT``.

Regla del proyecto: **ninguna función de fsops recibe una ruta cruda**. Todas
reciben una ruta ya pasada por :func:`resolve`. Concentrar la validación en un
solo sitio es lo que hace que sea auditable.

Nota sobre la suplantación: aunque un usuario lograra salirse del jail, Windows
seguiría aplicando sus permisos reales sobre el destino. El jail no es la única
defensa, es la primera. Las dos capas juntas son lo que da la garantía.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

from . import config
from .errors import InvalidPathName, PathOutsideJail

#: Caracteres que Windows prohíbe en un nombre de archivo.
#: Los dos puntos importan especialmente: habilitan los flujos de datos
#: alternativos de NTFS ("archivo.txt:oculto"), que permiten esconder
#: contenido dentro de un archivo aparentemente normal.
_CARACTERES_PROHIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

#: Nombres de dispositivo reservados por Windows. Siguen siendo reservados
#: aunque lleven extensión: "CON.txt" también falla.
_NOMBRES_RESERVADOS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def validar_nombre(nombre: str) -> str:
    """
    Valida un único componente de ruta (no una ruta completa).

    :raises InvalidPathName: si Windows no lo aceptaría o es peligroso.
    """
    if not nombre or not nombre.strip():
        raise InvalidPathName("El nombre no puede estar vacío")

    if nombre in (".", ".."):
        raise InvalidPathName("Nombre reservado por el sistema de archivos")

    if _CARACTERES_PROHIBIDOS.search(nombre):
        raise InvalidPathName(
            r'El nombre no puede contener < > : " / \ | ? * ni caracteres de control'
        )

    # Windows elimina silenciosamente los puntos y espacios finales al crear el
    # archivo. Eso significa que "informe.txt " y "informe.txt" acaban siendo el
    # mismo archivo, lo que permite burlar comprobaciones por nombre.
    if nombre != nombre.rstrip(". "):
        raise InvalidPathName("El nombre no puede terminar en punto ni en espacio")

    if nombre.split(".")[0].upper() in _NOMBRES_RESERVADOS:
        raise InvalidPathName(
            f"'{nombre}' usa un nombre de dispositivo reservado por Windows"
        )

    if len(nombre) > 255:
        raise InvalidPathName("El nombre supera los 255 caracteres")

    return nombre


def resolve(ruta_virtual: str, *, root: Path | None = None) -> Path:
    """
    Convierte una ruta virtual del cliente en una ruta física validada.

    El cliente siempre habla en rutas tipo POSIX relativas a la raíz:
    ``"documentos/informe.txt"``. Nunca ve ni envía rutas de Windows.

    :param ruta_virtual: ruta relativa a la raíz. "" o "/" es la raíz misma.
    :raises InvalidPathName: algún componente es inválido.
    :raises PathOutsideJail: la ruta resuelta se sale de la raíz.
    """
    root = (root or config.STORAGE_ROOT).resolve()

    limpia = (ruta_virtual or "").replace("\\", "/").strip("/")
    if not limpia:
        return root

    partes = [p for p in PurePosixPath(limpia).parts if p not in (".",)]

    # Rechazamos ".." explícitamente en vez de dejar que resolve() lo normalice.
    # Un cliente legítimo jamás lo envía: si aparece, es un intento de fuga y
    # queremos que quede registrado como tal, no silenciosamente corregido.
    if any(p == ".." for p in partes):
        raise PathOutsideJail("Las rutas no pueden contener '..'")

    for parte in partes:
        validar_nombre(parte)

    destino = (root / Path(*partes)).resolve()

    # La comprobación definitiva, hecha DESPUÉS de resolve(). Esto es lo que
    # neutraliza los enlaces simbólicos y las uniones de directorio (junctions):
    # si algún componente apuntaba fuera, resolve() lo revela y aquí se corta.
    if destino != root and root not in destino.parents:
        raise PathOutsideJail("La ruta queda fuera del área permitida")

    return destino


def to_virtual(ruta_fisica: Path, *, root: Path | None = None) -> str:
    """
    Inversa de :func:`resolve`: ruta física -> ruta virtual para el cliente.

    Nunca devolvemos rutas absolutas de Windows al cliente. Filtrarlas revela
    la estructura del servidor y no le sirve de nada a la interfaz.
    """
    root = (root or config.STORAGE_ROOT).resolve()
    ruta_fisica = Path(ruta_fisica).resolve()
    if ruta_fisica == root:
        return "/"
    return "/" + ruta_fisica.relative_to(root).as_posix()
