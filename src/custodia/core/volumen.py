# -*- coding: utf-8 -*-
"""
Verificación del cifrado de volumen (control C15, riesgo R1).

El cifrado de archivos no basta frente al robo del disco completo: la clave
maestra está protegida con secretos que viven en ese mismo disco. BitLocker
cubre ese caso. La aplicación no puede activarlo por sí sola, pero sí comprobar
si está activo y, si así se configura, negarse a abrir.

Solo se considera protegida la unidad con `ProtectionStatus` 1. Con cualquier
fallo de la consulta el resultado es "desconocido", nunca una excepción.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from . import audit, config

PROTEGIDO = "protegido"
SIN_PROTEGER = "sin_proteger"
DESCONOCIDO = "desconocido"

_ESPACIO_WMI = r"root\CIMV2\Security\MicrosoftVolumeEncryption"
_ESTADOS = {0: SIN_PROTEGER, 1: PROTEGIDO}


@dataclass
class Evaluacion:
    """Resultado de la comprobación al iniciar la aplicación."""

    estado: str
    bloquear: bool = False
    #: Qué hacer al respecto; vacío si no hay nada que hacer.
    mensaje: str = ""


_ultima: Evaluacion | None = None


def _consultar_wmi(unidad: str) -> int | None:
    """
    Hace la consulta. Va aparte, y sin dejar escapar excepciones, para que todos
    los objetos COM mueran con este marco, antes de `CoUninitialize`. Liberarlos
    después es un acceso inválido a memoria.
    """
    import win32com.client

    try:
        servicio = win32com.client.GetObject(
            "winmgmts:{impersonationLevel=impersonate,authenticationLevel=pktPrivacy}!"
            rf"\\.\{_ESPACIO_WMI}"
        )
        for volumen in servicio.ExecQuery(
            "SELECT ProtectionStatus FROM Win32_EncryptableVolume "
            f"WHERE DriveLetter = '{unidad}'"
        ):
            return int(volumen.ProtectionStatus)
    except Exception:
        pass
    return None


def _proteccion_wmi(unidad: str) -> int | None:
    """`ProtectionStatus` de la unidad; None si falla o WMI no la conoce."""
    import pythoncom

    pythoncom.CoInitialize()
    try:
        return _consultar_wmi(unidad)
    finally:
        pythoncom.CoUninitialize()


def _unidad_de(ruta: Path | str) -> str | None:
    """
    «C:» para una ruta local; None para una ruta de red.

    `abspath` y no `resolve`: este no toca el disco, y en una ruta de red
    `resolve` puede demorar segundos el arranque.
    """
    unidad = Path(os.path.abspath(ruta)).drive
    return unidad.upper() if re.fullmatch(r"[A-Za-z]:", unidad) else None


def estado_bitlocker(ruta: Path | str) -> str:
    """"protegido", "sin_proteger" o "desconocido". Nunca lanza."""
    try:
        unidad = _unidad_de(ruta)
        if unidad is None:
            return DESCONOCIDO
        return _ESTADOS.get(_proteccion_wmi(unidad), DESCONOCIDO)
    except Exception:
        return DESCONOCIDO


def _mensaje_sin_proteger(unidad: str) -> str:
    return (
        f"La unidad {unidad}, donde está el almacén, no tiene BitLocker activo: "
        "si roban el disco, la clave de los archivos queda a su alcance. Actívalo "
        "en Configuración > Privacidad y seguridad > Cifrado del dispositivo, o en "
        "Panel de control > Cifrado de unidad BitLocker en las ediciones Pro."
    )


def evaluar_arranque(ruta: Path | str | None = None) -> Evaluacion:
    """
    Comprueba la unidad del almacén al iniciar y recuerda el resultado.

    Una unidad sin proteger queda en la bitácora. Solo bloquea la entrada con
    EXIGIR_BITLOCKER y un estado confirmado: "desconocido" no bloquea, porque
    un fallo de WMI no debe dejar a nadie fuera de sus archivos.
    """
    global _ultima

    destino = ruta or config.STORAGE_ROOT
    estado = estado_bitlocker(destino)
    evaluacion = Evaluacion(estado)

    if estado == SIN_PROTEGER:
        unidad = _unidad_de(destino) or "del almacén"
        audit.registrar("sistema", "volumen_sin_proteger", exito=False,
                        detalle=f"unidad {unidad}")
        evaluacion.bloquear = config.EXIGIR_BITLOCKER
        evaluacion.mensaje = _mensaje_sin_proteger(unidad)

    _ultima = evaluacion
    return evaluacion


def ultima_evaluacion() -> Evaluacion | None:
    """El resultado de la comprobación hecha al arrancar, sin volver a consultar."""
    return _ultima
