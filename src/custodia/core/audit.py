# -*- coding: utf-8 -*-
"""
Bitácora de auditoría (RF-05).

Lo único que queda en base de datos en todo el proyecto. Los archivos los
guarda NTFS, las cuentas las guarda la SAM, y aquí solo se registra qué pasó.

SQLite y no MySQL: no hay servidor que instalar ni credenciales que configurar,
el archivo viaja con la aplicación, y para escrituras secuenciales de una sola
aplicación es más que suficiente.

------------------------------------------------------------------------------
Por qué la escritura es asíncrona
------------------------------------------------------------------------------
Las operaciones sobre archivos ocurren dentro de un bloque de suplantación. Si
la bitácora se escribiera ahí mismo, la escritura en SQLite pasaría por los
permisos del usuario suplantado, que no tiene ninguno sobre la carpeta de la
aplicación. La operación fallaría, o peor: habría que darle permiso de
escritura sobre el archivo de bitácora, y entonces cualquier usuario podría
manipular el registro de sus propias acciones. **Una bitácora que el auditado
puede editar no sirve de nada.**

La solución es separar quién anota de quién escribe. `registrar` solo encola el
evento en memoria, cosa que no toca el disco y puede hacerse desde cualquier
identidad. Un hilo escritor, que nunca suplanta a nadie, vacía la cola con los
privilegios de la aplicación.

Como efecto secundario, la operación del usuario no espera a que se escriba en
disco: encolar es inmediato.
"""
from __future__ import annotations

import queue
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import config

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    momento     TEXT    NOT NULL,
    usuario     TEXT    NOT NULL,
    accion      TEXT    NOT NULL,
    ruta        TEXT,
    exito       INTEGER NOT NULL,
    detalle     TEXT
);
CREATE INDEX IF NOT EXISTS idx_eventos_momento ON eventos(momento);
CREATE INDEX IF NOT EXISTS idx_eventos_usuario ON eventos(usuario);
"""

_SENTINELA_FLUSH = "__flush__"
_SENTINELA_PARAR = "__parar__"

_conn: sqlite3.Connection | None = None
_cola: "queue.Queue | None" = None
_hilo: threading.Thread | None = None
_lock = threading.Lock()


def init(ruta_db: Path | None = None) -> None:
    """
    Abre la base de datos y arranca el hilo escritor.

    Llamar al arrancar la aplicación, **antes de suplantar a nadie**: el
    archivo se abre aquí, con la identidad privilegiada.
    """
    global _conn, _cola, _hilo

    close()   # idempotente: reiniciar no deja dos hilos escribiendo

    ruta = Path(ruta_db or config.AUDIT_DB)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    _conn = sqlite3.connect(str(ruta), check_same_thread=False)
    _conn.executescript(_ESQUEMA)
    _conn.commit()

    _cola = queue.Queue()
    _hilo = threading.Thread(target=_escritor, name="custodia-auditoria",
                             daemon=True)
    _hilo.start()


def _escritor() -> None:
    """
    Bucle del hilo escritor.

    Nunca suplanta: conserva siempre la identidad de la aplicación, que es la
    única con permiso sobre el archivo de bitácora.
    """
    cola, conn = _cola, _conn
    if cola is None or conn is None:
        return

    while True:
        evento = cola.get()
        try:
            if isinstance(evento, tuple) and evento[0] == _SENTINELA_FLUSH:
                conn.commit()
                evento[1].set()
                continue
            if evento == _SENTINELA_PARAR:
                conn.commit()
                return

            conn.execute(
                "INSERT INTO eventos (momento, usuario, accion, ruta, exito, detalle) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                evento,
            )
            conn.commit()
        except Exception:
            # Un fallo al escribir la bitácora no debe tumbar el hilo ni la
            # operación del usuario. Se pierde el registro, no el trabajo.
            pass
        finally:
            cola.task_done()


def registrar(usuario: str, accion: str, ruta: str | None = None,
              exito: bool = True, detalle: str = "") -> None:
    """
    Anota un evento. Puede llamarse desde dentro de una suplantación.

    Solo encola: no toca el disco, así que no pasa por los permisos del usuario
    suplantado. Nunca lanza excepción.
    """
    if _cola is None:
        return
    try:
        _cola.put_nowait((
            datetime.now(timezone.utc).isoformat(),
            usuario,
            accion,
            ruta,
            1 if exito else 0,
            (detalle or "")[:1000],
        ))
    except Exception:
        pass


def flush(timeout: float = 5.0) -> bool:
    """
    Espera a que la cola se vacíe y se confirme en disco.

    Necesario antes de consultar la bitácora y en las pruebas: entre encolar y
    escribir hay un instante en que el evento existe en memoria pero todavía no
    en la base de datos.

    :return: True si se vació dentro del plazo.
    """
    if _cola is None:
        return True
    marca = threading.Event()
    _cola.put((_SENTINELA_FLUSH, marca))
    return marca.wait(timeout)


def close() -> None:
    """Vacía la cola, detiene el hilo y cierra la base de datos."""
    global _conn, _cola, _hilo

    with _lock:
        if _cola is not None and _hilo is not None and _hilo.is_alive():
            flush()
            _cola.put(_SENTINELA_PARAR)
            _hilo.join(timeout=5.0)

        if _conn is not None:
            try:
                _conn.close()
            except Exception:
                pass

        _conn = None
        _cola = None
        _hilo = None


def consultar(usuario: str | None = None, accion: str | None = None,
              solo_denegados: bool = False, limite: int = 100) -> list[dict]:
    """
    Últimos eventos, con filtros opcionales.

    `solo_denegados` es el filtro más útil en la práctica: responde a la
    pregunta "quién intentó acceder a algo que no le correspondía".
    """
    if _conn is None:
        return []

    flush()

    condiciones: list[str] = []
    params: list = []
    if usuario:
        condiciones.append("usuario = ?")
        params.append(usuario)
    if accion:
        condiciones.append("accion = ?")
        params.append(accion)
    if solo_denegados:
        condiciones.append("exito = 0")

    sql = "SELECT momento, usuario, accion, ruta, exito, detalle FROM eventos"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)

    filas = _conn.execute(sql, params).fetchall()
    return [
        {
            "momento": f[0], "usuario": f[1], "accion": f[2],
            "ruta": f[3], "exito": bool(f[4]), "detalle": f[5],
        }
        for f in filas
    ]
