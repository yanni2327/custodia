# -*- coding: utf-8 -*-
"""
Estructura del almacén y permisos iniciales.

Aquí se traduce a permisos NTFS el escenario de la propuesta: usuarios estándar
con acceso limitado a sus propios directorios, y un grupo administrativo con
acceso a toda la estructura.

------------------------------------------------------------------------------
El reparto
------------------------------------------------------------------------------
**La raíz.** Los usuarios reciben únicamente *recorrido* (atravesarla para
llegar a su carpeta y a la compartida), sin herencia. No pueden listarla ni
crear nada en ella: así no ven siquiera los nombres de las carpetas de otras
personas ni pueden fabricarse espacios propios fuera del suyo. Que no se
herede es lo importante: el permiso no baja a lo que haya dentro.

**Espacio personal.** Cada usuario tiene una carpeta con su nombre y control
total sobre ella, con la herencia rota para que nadie más la alcance por
arrastre. Es el "sus propios directorios" del caso de estudio.

**Carpeta compartida.** Lectura y escritura para todo el grupo de usuarios,
concedidas *al grupo* y no a cada persona. Es la demostración más clara de por
qué el token importa: cuando se añade a alguien al grupo, obtiene el acceso sin
tocar una sola ACL, porque Windows resuelve la pertenencia al emitir el token.

Todas estas operaciones escriben ACL, así que exigen privilegios de
administrador y se ejecutan **sin suplantar a nadie**.
"""
from __future__ import annotations

from pathlib import Path

import ntsecuritycon as con
import win32security

from . import acl, config
from .acl import Perm
from .errors import AccountError

#: Crear subcarpetas dentro de un directorio. No está en `Perm` porque solo
#: tiene sentido sobre contenedores.
_CREAR_SUBCARPETAS = getattr(con, "FILE_ADD_SUBDIRECTORY", 0x0004)
_CREAR_ARCHIVOS = getattr(con, "FILE_ADD_FILE", 0x0002)

#: Lo que un usuario necesita en la raíz: atravesarla para llegar a su carpeta
#: y a la compartida. NO listarla (vería los nombres de las carpetas ajenas) ni
#: crear subcarpetas (podría fabricarse espacios fuera del suyo). Su espacio
#: personal lo crea la aplicación con privilegios, no el usuario.
_PERMISO_EN_RAIZ = int(Perm.EJECUTAR)

#: Nombre de la carpeta común.
COMPARTIDA = "Compartida"


def preparar_raiz() -> None:
    """
    Crea el almacén y escribe su lista de permisos. Idempotente.

    Se rompe la herencia: sin eso, la carpeta heredaría los permisos de
    ``C:\\ProgramData``, donde el grupo Usuarios de Windows tiene lectura, y
    cualquier cuenta de la máquina podría leer el almacén entero.
    """
    config.STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

    acl.establecer_permisos(
        config.STORAGE_ROOT,
        [
            # Heredables: quien administra llega a todo el árbol.
            ("Administrators", int(Perm.TOTAL), True, True),
            ("SYSTEM", int(Perm.TOTAL), True, True),
            (config.ADMIN_GROUP, int(Perm.TOTAL), True, True),
            # Sin herencia: entrar en la raíz no da acceso a lo que contiene.
            (config.APP_GROUP, _PERMISO_EN_RAIZ, True, False),
        ],
        romper_herencia=True,
    )


def preparar_compartida() -> Path:
    """Crea la carpeta común, con acceso para todo el grupo de usuarios."""
    carpeta = config.STORAGE_ROOT / COMPARTIDA
    carpeta.mkdir(parents=True, exist_ok=True)

    acl.establecer_permisos(
        carpeta,
        [
            ("Administrators", int(Perm.TOTAL), True, True),
            (config.ADMIN_GROUP, int(Perm.TOTAL), True, True),
            # Al grupo, no a cada persona: añadir a alguien al grupo le da
            # acceso sin tocar esta lista.
            (config.APP_GROUP,
             int(Perm.LEER) | int(Perm.ESCRIBIR) | int(Perm.EJECUTAR)
             | _CREAR_ARCHIVOS | _CREAR_SUBCARPETAS,
             True, True),
        ],
        romper_herencia=True,
    )
    return carpeta


def ruta_personal(username: str) -> Path:
    """Dónde vive el espacio de un usuario."""
    return config.STORAGE_ROOT / username


def asegurar_espacio(username: str) -> Path:
    """
    Crea el espacio personal del usuario si no existe. Idempotente.

    Se llama al crear la cuenta y también al iniciar sesión, para que las
    cuentas creadas antes de que existiera esta función también lo tengan.
    """
    carpeta = ruta_personal(username)
    carpeta.mkdir(parents=True, exist_ok=True)

    try:
        acl.establecer_permisos(
            carpeta,
            [
                ("Administrators", int(Perm.TOTAL), True, True),
                (config.ADMIN_GROUP, int(Perm.TOTAL), True, True),
                (username, int(Perm.TOTAL), True, True),
            ],
            romper_herencia=True,
        )
    except AccountError:
        # La cuenta no existe en Windows. La carpeta queda solo para
        # administradores, que es el comportamiento seguro.
        pass

    # El usuario pasa a ser el propietario de su espacio. En Windows el
    # propietario siempre conserva el derecho de leer y cambiar la DACL, así
    # que nunca puede quedar excluido de su propia carpeta por error.
    try:
        acl.cambiar_propietario(carpeta, username)
    except Exception:
        pass

    return carpeta


def preparar_todo(usuarios: list[str] | None = None) -> None:
    """Deja el almacén listo: raíz, carpeta común y espacios personales."""
    preparar_raiz()
    preparar_compartida()
    for username in usuarios or []:
        asegurar_espacio(username)
