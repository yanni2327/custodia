# -*- coding: utf-8 -*-
"""
Defensa contra fuerza bruta en el inicio de sesión.

Windows ya tiene su propia política de bloqueo de cuentas, pero no siempre está
activada y no cubre el segundo factor de Custodia. Esta capa cuenta los intentos
fallidos por usuario y, superado el umbral dentro de una ventana, bloquea la
cuenta un tiempo. Cada bloqueo queda en la bitácora.

El registro se guarda en un archivo con la misma ACL que la clave maestra
(Administradores y SYSTEM), para que un usuario normal no pueda borrarlo y
reiniciar su propio contador.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import audit, config, crypto


def _cargar() -> dict:
    ruta = Path(config.INTENTOS_FILE)
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text("utf-8"))
    except Exception:
        return {}


def _guardar(datos: dict) -> None:
    ruta = Path(config.INTENTOS_FILE)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), "utf-8")
    try:
        crypto.proteger_solo_admin(ruta)
    except Exception:
        # Proteger el archivo es defensa en profundidad; si fallara, no debe
        # impedir el inicio de sesión.
        pass


def esta_bloqueado(usuario: str) -> tuple[bool, int]:
    """:return: (bloqueado, segundos que faltan para desbloquear)."""
    entrada = _cargar().get(usuario.lower())
    if not entrada:
        return (False, 0)
    restante = int(entrada.get("bloqueado_hasta", 0) - time.time())
    return (restante > 0, max(restante, 0))


def registrar_fallo(usuario: str) -> tuple[bool, int]:
    """
    Anota un intento fallido y bloquea la cuenta si se superó el umbral.

    :return: (quedó bloqueada ahora, segundos de bloqueo).
    """
    ahora = time.time()
    ventana = config.VENTANA_INTENTOS_MIN * 60
    datos = _cargar()
    entrada = datos.get(usuario.lower(), {"fallos": [], "bloqueado_hasta": 0})

    entrada["fallos"] = [t for t in entrada.get("fallos", []) if ahora - t < ventana]
    entrada["fallos"].append(ahora)

    bloqueado, restante = False, 0
    if len(entrada["fallos"]) >= config.MAX_INTENTOS:
        restante = config.BLOQUEO_MIN * 60
        entrada["bloqueado_hasta"] = ahora + restante
        entrada["fallos"] = []
        bloqueado = True
        audit.registrar(usuario, "bloqueo", exito=False,
                        detalle=f"{config.MAX_INTENTOS} intentos fallidos")

    datos[usuario.lower()] = entrada
    _guardar(datos)
    return (bloqueado, restante)


def limpiar(usuario: str) -> None:
    """Borra el historial de intentos de una cuenta tras un acceso correcto."""
    datos = _cargar()
    if datos.pop(usuario.lower(), None) is not None:
        _guardar(datos)
