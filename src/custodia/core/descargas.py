# -*- coding: utf-8 -*-
"""
Protección de la exportación de copias.

Con el cifrado por usuario, Custodia es el único que puede entregar un archivo
en claro: en disco todo está cifrado. Por eso la acción de "Guardar copia" es el
grifo real de fuga de contenido legible, y conviene reforzarla. Este módulo da
dos cosas:

1. **Clave de descarga.** Un segundo secreto, distinto del de inicio de sesión,
   que se pide antes de exportar. Así, aunque alguien se cuele en una sesión
   abierta, no puede sacar copias sin conocer también esta clave. Se guarda solo
   su **hash con scrypt**; de ahí no se puede volver a la clave, y la clave nunca
   se escribe ni se registra en claro.

2. **Límite anti-descarga-masiva.** Se cuentan las descargas por usuario; pasado
   el umbral en una ventana, se bloquean nuevas descargas un rato y queda una
   alerta en la bitácora. Frena a quien intenta llevarse todo de golpe.

El archivo de estado lleva la misma ACL que la clave maestra (Administradores y
SYSTEM), para que un usuario normal no pueda borrarlo ni leer los hashes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from . import audit, config, crypto

_SCRYPT = dict(n=2 ** 14, r=8, p=1, dklen=32)


def _cargar() -> dict:
    ruta = Path(config.DESCARGAS_FILE)
    if not ruta.exists():
        return {}
    try:
        return json.loads(ruta.read_text("utf-8"))
    except Exception:
        return {}


def _guardar(datos: dict) -> None:
    ruta = Path(config.DESCARGAS_FILE)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos), "utf-8")
    try:
        crypto.proteger_solo_admin(ruta)
    except Exception:
        pass


# -- clave de descarga ------------------------------------------------------

def _hash(clave: str, sal: bytes) -> bytes:
    return hashlib.scrypt(clave.encode("utf-8"), salt=sal, **_SCRYPT)


def tiene_clave(usuario: str) -> bool:
    entrada = _cargar().get(usuario.lower())
    return bool(entrada and entrada.get("hash"))


def establecer_clave(usuario: str, clave: str) -> None:
    store = _cargar()
    entrada = store.get(usuario.lower(), {})
    sal = os.urandom(16)
    entrada["sal"] = base64.b64encode(sal).decode("ascii")
    entrada["hash"] = base64.b64encode(_hash(clave, sal)).decode("ascii")
    store[usuario.lower()] = entrada
    _guardar(store)


def quitar_clave(usuario: str) -> None:
    store = _cargar()
    entrada = store.get(usuario.lower())
    if entrada:
        entrada.pop("sal", None)
        entrada.pop("hash", None)
        store[usuario.lower()] = entrada
        _guardar(store)


def verificar_clave(usuario: str, clave: str) -> bool:
    entrada = _cargar().get(usuario.lower())
    if not entrada or not entrada.get("hash"):
        return False
    sal = base64.b64decode(entrada["sal"])
    esperado = base64.b64decode(entrada["hash"])
    return hmac.compare_digest(_hash(clave, sal), esperado)


# -- límite anti-descarga-masiva --------------------------------------------

def estado(usuario: str) -> tuple[bool, int]:
    """:return: (bloqueado, segundos que faltan para poder descargar)."""
    entrada = _cargar().get(usuario.lower(), {})
    restante = int(entrada.get("bloqueado_hasta", 0) - time.time())
    return (restante > 0, max(restante, 0))


def registrar(usuario: str, recurso: str = "", motivo: str = "") -> tuple[bool, int]:
    """
    Anota una descarga y aplica el límite. Registra el evento y el motivo (no
    la clave). :return: (quedó bloqueado, segundos de bloqueo).
    """
    ahora = time.time()
    ventana = config.VENTANA_DESCARGAS_MIN * 60
    store = _cargar()
    entrada = store.get(usuario.lower(), {})
    entrada["descargas"] = [t for t in entrada.get("descargas", []) if ahora - t < ventana]
    entrada["descargas"].append(ahora)

    bloqueado, restante = False, 0
    if len(entrada["descargas"]) >= config.MAX_DESCARGAS:
        restante = config.BLOQUEO_DESCARGAS_MIN * 60
        entrada["bloqueado_hasta"] = ahora + restante
        entrada["descargas"] = []
        bloqueado = True
        audit.registrar(usuario, "descarga_masiva", recurso, exito=False,
                        detalle=f"más de {config.MAX_DESCARGAS} descargas")

    store[usuario.lower()] = entrada
    _guardar(store)
    audit.registrar(usuario, "descarga", recurso, exito=True,
                    detalle=(motivo or "")[:200])
    return (bloqueado, restante)
