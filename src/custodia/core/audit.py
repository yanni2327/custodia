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

------------------------------------------------------------------------------
Encadenamiento (C16, esquema de Schneier y Kelsey)
------------------------------------------------------------------------------
Cada registro guarda el SHA-256 de su propio contenido y del hash del registro
anterior: alterar o borrar uno rompe la cadena desde ahí. Solo el hilo escritor
calcula los hash, dentro de la transacción del INSERT, así que no hay carreras.

Quien controle el archivo podría recalcular toda la cadena. Por eso, cada
`INTERVALO_ANCLA` eventos y al cerrar, el último id y su hash se copian al Visor
de eventos de Windows: un recálculo o un borrado del final dejan una diferencia
con esas anclas.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import sqlite3
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import win32evtlog
import win32evtlogutil

from . import config

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS eventos (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    momento       TEXT    NOT NULL,
    usuario       TEXT    NOT NULL,
    accion        TEXT    NOT NULL,
    ruta          TEXT,
    exito         INTEGER NOT NULL,
    detalle       TEXT,
    hash_anterior TEXT,
    hash          TEXT
);
CREATE INDEX IF NOT EXISTS idx_eventos_momento ON eventos(momento);
CREATE INDEX IF NOT EXISTS idx_eventos_usuario ON eventos(usuario);
"""

#: `hash_anterior` del primer registro de la cadena.
GENESIS = "0" * 64

#: Cada cuántos eventos se copia el último hash al Visor de eventos.
INTERVALO_ANCLA = 50

#: Segundos que `close` espera a que el hilo escritor termine.
_ESPERA_AL_CERRAR = 5.0

ORIGEN_ANCLA = "Custodia"
_ID_EVENTO_ANCLA = 1
_PATRON_ANCLA = re.compile(r"bitacora=([0-9a-f]{16}) id=(\d+) hash=([0-9a-f]{64})")

_SENTINELA_FLUSH = "__flush__"
_SENTINELA_PARAR = "__parar__"

_conn: sqlite3.Connection | None = None
_cola: "queue.Queue | None" = None
_hilo: threading.Thread | None = None
_ruta_db: Path | None = None
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Cadena de hash
# ---------------------------------------------------------------------------

def _hash_registro(id_: int, momento: str, usuario: str, accion: str,
                   ruta: str | None, exito: int, detalle: str | None,
                   hash_anterior: str | None) -> str:
    """
    SHA-256 de una serialización canónica.

    Un arreglo JSON no es ambiguo: delimita cada campo y distingue NULL de la
    cadena vacía, cosa que concatenar con un separador no garantiza.
    """
    canonico = json.dumps(
        [id_, momento, usuario, accion, ruta, exito, detalle, hash_anterior],
        ensure_ascii=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonico.encode("ascii")).hexdigest()


def _encadenar(conn: sqlite3.Connection, evento: tuple) -> tuple[int, str]:
    """Inserta un evento al final de la cadena. Debe ir dentro de una transacción."""
    fila = conn.execute("SELECT hash FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
    anterior = fila[0] if fila and fila[0] else GENESIS
    id_ = conn.execute(
        "INSERT INTO eventos (momento, usuario, accion, ruta, exito, detalle, hash_anterior) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (*evento, anterior),
    ).lastrowid
    # El id lo asigna SQLite y forma parte del hash, por eso son dos pasos.
    hash_ = _hash_registro(id_, *evento, anterior)
    conn.execute("UPDATE eventos SET hash = ? WHERE id = ?", (hash_, id_))
    return id_, hash_


def _migrar(conn: sqlite3.Connection) -> None:
    """Encadena en orden de id una base anterior a C16. Todo o nada."""
    if "hash" in {f[1] for f in conn.execute("PRAGMA table_info(eventos)")}:
        return

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("ALTER TABLE eventos ADD COLUMN hash_anterior TEXT")
        conn.execute("ALTER TABLE eventos ADD COLUMN hash TEXT")
        filas = conn.execute(
            "SELECT id, momento, usuario, accion, ruta, exito, detalle "
            "FROM eventos ORDER BY id"
        ).fetchall()
        anterior = GENESIS
        for fila in filas:
            hash_ = _hash_registro(*fila, anterior)
            conn.execute("UPDATE eventos SET hash_anterior = ?, hash = ? WHERE id = ?",
                         (anterior, hash_, fila[0]))
            anterior = hash_

        if filas:
            desde = filas[0][0]
        else:
            secuencia = conn.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'eventos'").fetchone()
            desde = (secuencia[0] if secuencia else 0) + 1
        _encadenar(conn, (datetime.now(timezone.utc).isoformat(), "sistema",
                          "cadena_iniciada", None, 1, f"cadena desde id {desde}"))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------------
# Anclas en el Visor de eventos
# ---------------------------------------------------------------------------

def _marca_bitacora(ruta: Path) -> str:
    """Identifica a qué bitácora pertenece un ancla, por su ruta."""
    normal = os.path.normcase(str(Path(ruta).resolve()))
    return hashlib.sha256(normal.encode("utf-8")).hexdigest()[:16]


def _emitir_ancla(ruta: Path, id_: int, hash_: str) -> None:
    win32evtlogutil.ReportEvent(
        ORIGEN_ANCLA, _ID_EVENTO_ANCLA,
        eventType=win32evtlog.EVENTLOG_INFORMATION_TYPE,
        strings=[f"bitacora={_marca_bitacora(ruta)} id={id_} hash={hash_}"],
    )


def _leer_anclas(ruta: Path) -> list[tuple[int, str]]:
    """Todas las anclas de esta bitácora que conserva el Visor de eventos."""
    marca = _marca_bitacora(ruta)
    anclas: list[tuple[int, str]] = []
    registro = win32evtlog.OpenEventLog(None, "Application")
    banderas = win32evtlog.EVENTLOG_BACKWARDS_READ | win32evtlog.EVENTLOG_SEQUENTIAL_READ
    try:
        while True:
            lote = win32evtlog.ReadEventLog(registro, banderas, 0)
            if not lote:
                return anclas
            for evento in lote:
                if evento.SourceName != ORIGEN_ANCLA:
                    continue
                hallado = _PATRON_ANCLA.search(" ".join(evento.StringInserts or ()))
                if hallado and hallado.group(1) == marca:
                    anclas.append((int(hallado.group(2)), hallado.group(3)))
    finally:
        win32evtlog.CloseEventLog(registro)


def _anclar(ruta: Path, id_: int, hash_: str) -> None:
    """Un fallo del Visor de eventos no debe impedir escribir la bitácora."""
    if not config.ANCLAR_BITACORA:
        return
    try:
        _emitir_ancla(ruta, id_, hash_)
    except Exception:
        pass


def _registrar_origen() -> None:
    """
    Da de alta el origen «Custodia» para que el Visor muestre bien sus eventos.

    En el ejecutable no se hace: registraría una DLL de su carpeta temporal. Las
    anclas se escriben y se leen igual sin este registro.
    """
    if not config.ANCLAR_BITACORA or getattr(sys, "frozen", False):
        return
    try:
        win32evtlogutil.AddSourceToRegistry(ORIGEN_ANCLA, eventLogType="Application")
    except Exception:
        pass


def init(ruta_db: Path | None = None) -> None:
    """
    Abre la base de datos y arranca el hilo escritor.

    Llamar al arrancar la aplicación, **antes de suplantar a nadie**: el
    archivo se abre aquí, con la identidad privilegiada.
    """
    global _conn, _cola, _hilo, _ruta_db

    close()   # idempotente: reiniciar no deja dos hilos escribiendo

    ruta = Path(ruta_db or config.AUDIT_DB)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    _conn = sqlite3.connect(str(ruta), check_same_thread=False)
    _conn.executescript(_ESQUEMA)
    _migrar(_conn)
    _conn.commit()
    _ruta_db = ruta
    _registrar_origen()

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
    cola, conn, ruta = _cola, _conn, _ruta_db
    if cola is None or conn is None or ruta is None:
        return

    ultima_anclada = None

    while True:
        evento = cola.get()
        try:
            if isinstance(evento, tuple) and evento[0] == _SENTINELA_FLUSH:
                conn.commit()
                evento[1].set()
                continue
            if evento == _SENTINELA_PARAR:
                conn.commit()
                fila = conn.execute(
                    "SELECT id, hash FROM eventos ORDER BY id DESC LIMIT 1").fetchone()
                if fila and fila[0] != ultima_anclada and fila[1]:
                    _anclar(ruta, fila[0], fila[1])
                if _conn is not conn:   # `close` no esperó: la cierra este hilo
                    conn.close()
                return

            conn.execute("BEGIN IMMEDIATE")
            id_, hash_ = _encadenar(conn, evento)
            conn.commit()
            if id_ % INTERVALO_ANCLA == 0:
                _anclar(ruta, id_, hash_)
                ultima_anclada = id_
        except Exception:
            # Un fallo al escribir la bitácora no debe tumbar el hilo ni la
            # operación del usuario. Se pierde el registro, no el trabajo.
            if conn.in_transaction:
                conn.rollback()
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
            _hilo.join(timeout=_ESPERA_AL_CERRAR)

        # Si el escritor sigue vaciando la cola, la conexión todavía es suya:
        # cerrarla bajo sus pies tumbaría el proceso. Él la suelta al terminar.
        if _conn is not None and not (_hilo is not None and _hilo.is_alive()):
            try:
                _conn.close()
            except Exception:
                pass

        _conn = None
        _cola = None
        _hilo = None


@dataclass
class ResultadoCadena:
    """Resultado de `verificar_cadena`."""

    ok: bool
    total: int
    primer_id_roto: int | None = None
    #: editado, borrado, insertado, truncado, ancla_distinta o ilegible.
    motivo: str | None = None
    ultima_ancla: int | None = None
    aviso: str = ""


def _inicio_de_cadena(filas: list[tuple]) -> tuple[int, int]:
    """
    (id donde debe empezar la cadena, último id previo a la cadena).

    Los huecos anteriores a una migración ya existían y no se pueden juzgar:
    un borrado posterior igual rompe los hash.
    """
    for fila in filas:
        if fila[3] == "cadena_iniciada":
            hallado = re.search(r"desde id (\d+)", fila[6] or "")
            if hallado:
                return int(hallado.group(1)), fila[0]
    return 1, 0


def _revisar_filas(filas: list[tuple]) -> ResultadoCadena | None:
    """El primer punto roto de la cadena, o None si está íntegra."""
    inicio, ultimo_previo = _inicio_de_cadena(filas)
    id_previo, hash_previo = None, GENESIS

    for total, fila in enumerate(filas, 1):
        id_, *campos, hash_anterior, hash_ = fila
        propio_ok = bool(hash_) and hash_ == _hash_registro(id_, *campos, hash_anterior)
        enlace_ok = hash_anterior == hash_previo
        esperado = inicio if id_previo is None else id_previo + 1

        if not propio_ok:
            motivo = "editado" if enlace_ok else "insertado"
            return ResultadoCadena(False, total, id_, motivo)
        if id_ != esperado and not (id_ <= ultimo_previo and enlace_ok):
            return ResultadoCadena(False, total, esperado, "borrado")
        if not enlace_ok:
            return ResultadoCadena(False, total, id_, "insertado")

        id_previo, hash_previo = id_, hash_
    return None


def _comparar_anclas(filas: list[tuple], anclas: list[tuple[int, str]],
                     resultado: ResultadoCadena) -> None:
    resultado.ultima_ancla = max(a[0] for a in anclas)
    ultimo_id = filas[-1][0] if filas else 0
    if resultado.ultima_ancla > ultimo_id:
        resultado.ok = False
        resultado.primer_id_roto = ultimo_id + 1
        resultado.motivo = "truncado"
        return

    hash_por_id = {f[0]: f[-1] for f in filas}
    for id_, hash_ in sorted(anclas):
        if hash_por_id.get(id_) != hash_:
            resultado.ok = False
            resultado.primer_id_roto = id_
            resultado.motivo = "ancla_distinta"
            return


def verificar_cadena(ruta_db: Path | None = None) -> ResultadoCadena:
    """
    Recorre la bitácora y la compara con las anclas del Visor de eventos.

    Usa una conexión propia: la del hilo escritor podría estar a mitad de una
    transacción, con un registro insertado que todavía no tiene su hash.
    """
    flush()
    ruta = Path(ruta_db or _ruta_db or config.AUDIT_DB)
    try:
        lectura = sqlite3.connect(f"file:{ruta.as_posix()}?mode=ro", uri=True)
        try:
            filas = lectura.execute(
                "SELECT id, momento, usuario, accion, ruta, exito, detalle, "
                "hash_anterior, hash FROM eventos ORDER BY id"
            ).fetchall()
        finally:
            lectura.close()
    except sqlite3.Error as exc:
        return ResultadoCadena(False, 0, None, "ilegible", aviso=str(exc))

    roto = _revisar_filas(filas)
    if roto is not None:
        return roto

    resultado = ResultadoCadena(True, len(filas))
    try:
        anclas = _leer_anclas(ruta) if config.ANCLAR_BITACORA else []
    except Exception:
        resultado.aviso = "No se pudo leer el Visor de eventos para comparar las anclas."
        return resultado

    if anclas:
        _comparar_anclas(filas, anclas, resultado)
    else:
        resultado.aviso = "El Visor de eventos no tiene anclas de esta bitácora."
    return resultado


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
