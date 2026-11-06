# -*- coding: utf-8 -*-
"""
Suplantación de identidad (impersonation) de Windows.

Este es el módulo más importante del proyecto. Todo el argumento del trabajo
se apoya en él: la aplicación no decide quién puede hacer qué. Adopta la
identidad del usuario y deja que el kernel de Windows conteste.

    with impersonate(token):
        open(ruta).read()      # si no tiene permiso, PermissionError

El `if` que autoriza no existe en nuestro código. Lo pone Windows.

------------------------------------------------------------------------------
ADVERTENCIA CRÍTICA — leer antes de usar
------------------------------------------------------------------------------
En Windows la suplantación es **por hilo**, no por proceso. Consecuencias:

1. Si suplantas y no reviertes, el hilo queda contaminado. Como el servidor
   web reutiliza hilos de un pool, la siguiente petición podría ejecutarse con
   la identidad del usuario anterior. Sería un fallo de seguridad silencioso.
   Por eso `RevertToSelf()` va SIEMPRE en un `finally`.

2. Nunca uses este context manager dentro de una función `async`. Una corrutina
   puede suspenderse en un `await` y reanudarse en OTRO hilo, dejando la
   suplantación activa en el hilo original y ejecutando el resto del trabajo
   sin ella. Todos los endpoints que toquen archivos deben declararse con
   `def`, nunca con `async def`.

3. El proceso que llama necesita el privilegio SeImpersonatePrivilege. Los
   miembros de Administradores y la cuenta LocalSystem lo tienen; un usuario
   normal no. Por eso el servicio corre como Servicio de Windows.
"""
from __future__ import annotations

import contextlib
import threading
from typing import Iterator

import win32security
import pywintypes

from .errors import PermissionDenied

#: Marca por hilo para detectar suplantaciones anidadas, que son un error de
#: diseño: revertir la interna devolvería el hilo a la identidad del servicio,
#: no a la externa, y el resto del bloque correría con privilegios elevados.
_state = threading.local()


@contextlib.contextmanager
def impersonate(token) -> Iterator[None]:
    """
    Ejecuta el bloque con la identidad del token dado.

    :param token: handle devuelto por :func:`sopfs.auth.logon`.
    :raises RuntimeError: si ya hay una suplantación activa en este hilo.
    """
    if getattr(_state, "active", False):
        raise RuntimeError(
            "Suplantación anidada detectada. Revertir la interna devolvería el "
            "hilo a la identidad del servicio y el resto del bloque correría "
            "con privilegios elevados. Reestructura el código."
        )

    win32security.ImpersonateLoggedOnUser(token)
    _state.active = True
    try:
        yield
    finally:
        # Este finally no es opcional. Ver la advertencia de arriba.
        _state.active = False
        win32security.RevertToSelf()


def current_identity() -> str:
    """
    Devuelve el nombre de la identidad efectiva del hilo actual.

    Útil en pruebas y en la bitácora: dentro de un bloque `impersonate` debe
    devolver el usuario suplantado, y fuera, la cuenta del servicio.
    """
    import win32api

    return win32api.GetUserName()


def is_impersonating() -> bool:
    """True si este hilo está dentro de un bloque `impersonate`."""
    return bool(getattr(_state, "active", False))


def assert_impersonating() -> None:
    """
    Guardia para las funciones de fsops.

    Cualquier operación sobre archivos que se ejecute sin suplantación correría
    con los privilegios del servicio, que son administrativos. Eso saltaría por
    encima de todo el control de acceso. Fallar ruidosamente es preferible.
    """
    if not is_impersonating():
        raise RuntimeError(
            "Operación de archivos sin suplantación activa. Correría con los "
            "privilegios del servicio y saltaría el control de acceso."
        )


# Código de error de Windows para acceso denegado.
_ERROR_ACCESS_DENIED = 5


@contextlib.contextmanager
def translate_denials(path: str = "") -> Iterator[None]:
    """
    Traduce el "no" del kernel a :class:`PermissionDenied`.

    Envuelve las llamadas al sistema de archivos para que el resto de la
    aplicación no tenga que distinguir entre `PermissionError` de Python y
    `pywintypes.error` de las APIs nativas.
    """
    try:
        yield
    except PermissionError as exc:
        raise PermissionDenied(
            f"Windows denegó el acceso a {path or 'el recurso'}"
        ) from exc
    except OSError as exc:
        if getattr(exc, "winerror", None) == _ERROR_ACCESS_DENIED:
            raise PermissionDenied(
                f"Windows denegó el acceso a {path or 'el recurso'}"
            ) from exc
        raise
    except pywintypes.error as exc:
        if exc.winerror == _ERROR_ACCESS_DENIED:
            raise PermissionDenied(
                f"Windows denegó el acceso a {path or 'el recurso'}"
            ) from exc
        raise
