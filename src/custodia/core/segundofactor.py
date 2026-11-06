# -*- coding: utf-8 -*-
"""
Gestión del segundo factor (2FA) por usuario.

Cada cuenta puede activar un segundo factor TOTP. El secreto se guarda protegido
con DPAPI —el mismo mecanismo de la clave maestra— dentro de un archivo cuya ACL
solo permite Administradores y SYSTEM. Así, un usuario normal de la máquina no
puede leer el secreto de otro, y el blob no sirve copiado a otro equipo.

El archivo es un JSON que mapea usuario → secreto protegido (en base64). No
guarda nada en claro.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import win32crypt

from . import config, crypto, totp

#: Entropía adicional específica de esta función (ver crypto.py).
_ENTROPIA = b"Custodia/v1/segundo-factor"
_LOCAL_MACHINE = 0x4


def _proteger(secreto: str) -> str:
    blob = win32crypt.CryptProtectData(
        secreto.encode("ascii"), "Custodia: segundo factor",
        _ENTROPIA, None, None, _LOCAL_MACHINE,
    )
    return base64.b64encode(blob).decode("ascii")


def _desproteger(blob_b64: str) -> str:
    blob = base64.b64decode(blob_b64)
    _, secreto = win32crypt.CryptUnprotectData(blob, _ENTROPIA, None, None, 0)
    return secreto.decode("ascii")


def _cargar() -> dict:
    ruta = Path(config.SEGUNDO_FACTOR_FILE)
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text("utf-8"))
    except Exception:
        return {}


def _guardar(datos: dict) -> None:
    ruta = Path(config.SEGUNDO_FACTOR_FILE)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), "utf-8")
    crypto.proteger_solo_admin(ruta)


def esta_habilitado(usuario: str) -> bool:
    return usuario.lower() in _cargar()


def activar(usuario: str) -> tuple[str, str]:
    """
    Genera y guarda un secreto nuevo para la cuenta.

    :return: (secreto en base32, enlace otpauth) para mostrarlos al usuario una
        sola vez, mientras configura su app de autenticación.
    """
    secreto = totp.generar_secreto()
    datos = _cargar()
    datos[usuario.lower()] = _proteger(secreto)
    _guardar(datos)
    return secreto, totp.uri_otpauth(secreto, usuario, config.EMISOR_2FA)


def desactivar(usuario: str) -> None:
    datos = _cargar()
    if datos.pop(usuario.lower(), None) is not None:
        _guardar(datos)


def _secreto(usuario: str) -> str | None:
    blob = _cargar().get(usuario.lower())
    if not blob:
        return None
    try:
        return _desproteger(blob)
    except Exception:
        return None


def verificar(usuario: str, codigo: str) -> bool:
    secreto = _secreto(usuario)
    return bool(secreto) and totp.verificar(secreto, codigo)


def verificar_contador(usuario: str, codigo: str) -> int | None:
    """El contador del código si es válido (ver `totp.contador_valido`)."""
    secreto = _secreto(usuario)
    if not secreto:
        return None
    return totp.contador_valido(secreto, codigo)
