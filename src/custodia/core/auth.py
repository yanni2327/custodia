# -*- coding: utf-8 -*-
"""
Autenticación y sesiones.

Aquí está la segunda idea clave del proyecto: **no guardamos contraseñas**.
No hay tabla de usuarios con `password_hash`, no hay bcrypt, no hay nada que
se nos pueda filtrar. El cliente manda usuario y contraseña, se los pasamos a
`LogonUser`, y Windows valida contra su propia base de cuentas (la SAM).

Si las credenciales son correctas, Windows devuelve un *token de acceso*: un
objeto del kernel que representa a ese usuario con sus grupos y privilegios.
Ese token es lo que guardamos en memoria, y es lo que `impersonate()` usa
después para cada operación.
"""
from __future__ import annotations

import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import win32con
import win32security
import pywintypes

from . import config
from .errors import AuthenticationError, CambioDeContrasenaRequerido, SessionError

# Códigos de error de Windows que conviene distinguir para dar buenos mensajes.
_ERROR_LOGON_FAILURE = 1326        # usuario o contraseña incorrectos
_ERROR_ACCOUNT_DISABLED = 1331
_ERROR_ACCOUNT_LOCKED_OUT = 1909
_ERROR_PASSWORD_EXPIRED = 1330
_ERROR_PASSWORD_MUST_CHANGE = 1907  # «debe cambiar la contraseña» (temporal)
_ERROR_ACCOUNT_RESTRICTION = 1327  # p. ej. contraseña vacía no permitida


def logon(username: str, password: str, domain: str = "."):
    """
    Valida credenciales contra Windows y devuelve un token de acceso.

    Se usa ``LOGON32_LOGON_NETWORK`` porque:

    - Produce directamente un token de nivel *impersonation*, que es lo que
      necesita ``ImpersonateLoggedOnUser``.
    - Es el tipo de inicio de sesión más liviano: no carga el perfil del
      usuario ni crea una sesión interactiva.
    - No requiere que la cuenta tenga el derecho "Permitir el inicio de sesión
      local", que es lo que exigiría ``LOGON32_LOGON_INTERACTIVE``.

    Su limitación es que el token no sirve para saltar a recursos de red
    (no hay delegación), lo cual aquí da igual: todos los archivos son locales.

    :param domain: "." significa la máquina local. Este proyecto trabaja solo
        con cuentas locales, nunca con un dominio.
    :raises AuthenticationError: credenciales inválidas o cuenta no utilizable.
    """
    try:
        return win32security.LogonUser(
            username,
            domain,
            password,
            win32con.LOGON32_LOGON_NETWORK,
            win32con.LOGON32_PROVIDER_DEFAULT,
        )
    except pywintypes.error as exc:
        # Windows solo devuelve estos dos si la contraseña ERA correcta: la
        # persona demostró conocerla, pero debe cambiarla antes de entrar.
        if exc.winerror in (_ERROR_PASSWORD_MUST_CHANGE, _ERROR_PASSWORD_EXPIRED):
            raise CambioDeContrasenaRequerido() from exc
        mensajes = {
            _ERROR_LOGON_FAILURE: "Usuario o contraseña incorrectos",
            _ERROR_ACCOUNT_DISABLED: "La cuenta está deshabilitada",
            _ERROR_ACCOUNT_LOCKED_OUT: "La cuenta está bloqueada",
            _ERROR_PASSWORD_EXPIRED: "La contraseña expiró",
            _ERROR_ACCOUNT_RESTRICTION: (
                "La cuenta tiene una restricción que impide iniciar sesión "
                "(revisa si la contraseña está vacía)"
            ),
        }
        # Nota deliberada: no distinguimos "usuario no existe" de "contraseña
        # incorrecta" hacia el cliente. Hacerlo permitiría enumerar cuentas.
        raise AuthenticationError(
            mensajes.get(exc.winerror, f"No se pudo iniciar sesión (error {exc.winerror})")
        ) from exc


@dataclass
class Session:
    """Una sesión abierta: un token de Windows con metadatos."""

    id: str
    username: str
    token: object = field(repr=False)   # no queremos el handle en los logs
    created_at: datetime
    last_seen: datetime

    def touch(self) -> None:
        self.last_seen = datetime.now(timezone.utc)

    def is_idle(self, minutes: int) -> bool:
        return datetime.now(timezone.utc) - self.last_seen > timedelta(minutes=minutes)


class SessionStore:
    """
    Almacén de sesiones en memoria, seguro entre hilos.

    En memoria y no en base de datos a propósito: un token de acceso es un
    handle del kernel, no se puede serializar ni sobrevivir a un reinicio del
    servicio. Si el servicio cae, todos vuelven a autenticarse. Correcto.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.RLock()

    def create(self, username: str, password: str) -> Session:
        """Autentica y abre una sesión nueva."""
        token = logon(username, password)
        now = datetime.now(timezone.utc)
        session = Session(
            id=secrets.token_urlsafe(32),
            username=username,
            token=token,
            created_at=now,
            last_seen=now,
        )
        with self._lock:
            self._sessions[session.id] = session
        return session

    def get(self, session_id: str) -> Session:
        """
        Recupera una sesión válida y actualiza su marca de actividad.

        :raises SessionError: si no existe o expiró por inactividad.
        """
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise SessionError("Sesión inválida o expirada")
            if session.is_idle(config.SESSION_IDLE_MINUTES):
                self._close_locked(session_id)
                raise SessionError("Sesión expirada por inactividad")
            session.touch()
            return session

    def close(self, session_id: str) -> None:
        """Cierra una sesión y libera su token."""
        with self._lock:
            self._close_locked(session_id)

    def _close_locked(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session is not None and session.token is not None:
            # Liberar el handle del kernel. Sin esto, un servicio de larga
            # duración va acumulando handles hasta agotarlos.
            try:
                session.token.Close()
            except Exception:
                pass

    def sweep(self) -> int:
        """
        Cierra las sesiones inactivas. Llamar periódicamente desde el servicio.

        :return: cuántas se cerraron.
        """
        with self._lock:
            caducadas = [
                sid
                for sid, s in self._sessions.items()
                if s.is_idle(config.SESSION_IDLE_MINUTES)
            ]
            for sid in caducadas:
                self._close_locked(sid)
            return len(caducadas)

    def __len__(self) -> int:
        with self._lock:
            return len(self._sessions)


#: Instancia única usada por el servicio.
sessions = SessionStore()
