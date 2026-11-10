# -*- coding: utf-8 -*-
"""
Encadenamiento de la bitácora (C16).

Cada prueba manipula la base de datos con SQLite directo, como lo haría alguien
que abre `audit.db` por fuera de la aplicación.
"""
from __future__ import annotations

import sqlite3
import threading

import pytest

from conftest import pytestmark  # noqa: F401


def _llenar(n: int) -> None:
    from custodia.core import audit

    for i in range(n):
        audit.registrar("ana", "leer", f"/ana/{i}.txt", detalle=f"evento {i}")
    audit.flush()


def _sql(ruta, sentencia: str, *params) -> None:
    conn = sqlite3.connect(str(ruta))
    conn.execute(sentencia, params)
    conn.commit()
    conn.close()


def _fila(ruta, id_: int) -> tuple:
    conn = sqlite3.connect(str(ruta))
    fila = conn.execute("SELECT id, hash, hash_anterior FROM eventos WHERE id = ?",
                        (id_,)).fetchone()
    conn.close()
    return fila


def _recalcular(ruta, desde: int = 1) -> None:
    """Lo que haría un administrador que conoce el algoritmo."""
    from custodia.core import audit

    conn = sqlite3.connect(str(ruta))
    previo = conn.execute("SELECT hash FROM eventos WHERE id < ? ORDER BY id DESC LIMIT 1",
                          (desde,)).fetchone()
    anterior = previo[0] if previo else audit.GENESIS
    for f in conn.execute(
        "SELECT id, momento, usuario, accion, ruta, exito, detalle FROM eventos "
        "WHERE id >= ? ORDER BY id", (desde,)
    ).fetchall():
        nuevo = audit._hash_registro(*f, anterior)
        conn.execute("UPDATE eventos SET hash_anterior = ?, hash = ? WHERE id = ?",
                     (anterior, nuevo, f[0]))
        anterior = nuevo
    conn.commit()
    conn.close()


@pytest.fixture
def anclas(monkeypatch):
    """Visor de eventos en memoria, sin tocar el del equipo."""
    from custodia.core import audit, config

    guardadas: list[tuple[int, str]] = []
    monkeypatch.setattr(config, "ANCLAR_BITACORA", True)
    monkeypatch.setattr(audit, "_registrar_origen", lambda: None)
    monkeypatch.setattr(audit, "_emitir_ancla",
                        lambda ruta, id_, hash_: guardadas.append((id_, hash_)))
    monkeypatch.setattr(audit, "_leer_anclas", lambda ruta: list(guardadas))
    return guardadas


# ---------------------------------------------------------------------------
# Cadena
# ---------------------------------------------------------------------------

def test_cadena_valida(bitacora):
    from custodia.core import audit

    _llenar(10)
    resultado = audit.verificar_cadena()

    assert resultado.ok and resultado.total == 10
    assert resultado.primer_id_roto is None and resultado.motivo is None
    assert _fila(bitacora, 1)[2] == audit.GENESIS
    assert _fila(bitacora, 2)[2] == _fila(bitacora, 1)[1]


def test_bitacora_vacia_es_valida(bitacora):
    from custodia.core import audit

    resultado = audit.verificar_cadena()
    assert resultado.ok and resultado.total == 0


def test_la_serializacion_no_es_ambigua():
    from custodia.core import audit

    base = audit._hash_registro(1, "t", "ab", "c", None, 1, None, audit.GENESIS)
    assert base != audit._hash_registro(1, "t", "a", "bc", None, 1, None, audit.GENESIS)
    assert base != audit._hash_registro(1, "t", "ab", "c", "", 1, None, audit.GENESIS)
    assert base != audit._hash_registro(1, "t", "ab", "c", None, 1, "", audit.GENESIS)


@pytest.mark.parametrize("campo, valor", [
    ("momento", "2020-01-01T00:00:00+00:00"), ("usuario", "juan"), ("accion", "otra"),
    ("ruta", "/juan/x"), ("exito", 0), ("detalle", "manipulado"),
])
def test_editar_cualquier_campo(bitacora, campo, valor):
    from custodia.core import audit

    _llenar(5)
    _sql(bitacora, f"UPDATE eventos SET {campo} = ? WHERE id = 3", valor)

    resultado = audit.verificar_cadena()
    assert not resultado.ok
    assert (resultado.primer_id_roto, resultado.motivo) == (3, "editado")


def test_borrar_un_registro_del_medio(bitacora):
    from custodia.core import audit

    _llenar(5)
    _sql(bitacora, "DELETE FROM eventos WHERE id = 3")

    resultado = audit.verificar_cadena()
    assert not resultado.ok
    assert (resultado.primer_id_roto, resultado.motivo) == (3, "borrado")


def test_borrar_el_primero(bitacora):
    from custodia.core import audit

    _llenar(3)
    _sql(bitacora, "DELETE FROM eventos WHERE id = 1")

    resultado = audit.verificar_cadena()
    assert (resultado.primer_id_roto, resultado.motivo) == (1, "borrado")


def test_borrar_el_final_y_seguir_escribiendo_deja_un_hueco(bitacora):
    """AUTOINCREMENT no reutiliza ids: lo escrito después delata el borrado."""
    from custodia.core import audit

    _llenar(5)
    _sql(bitacora, "DELETE FROM eventos WHERE id > 3")
    _llenar(1)

    resultado = audit.verificar_cadena()
    assert (resultado.primer_id_roto, resultado.motivo) == (4, "borrado")


def test_insertar_uno_falso_sin_hash_valido(bitacora):
    from custodia.core import audit

    _llenar(3)
    _sql(bitacora,
         "INSERT INTO eventos (momento, usuario, accion, exito, hash_anterior, hash) "
         "VALUES ('t', 'falso', 'leer', 1, ?, ?)", "f" * 64, "e" * 64)

    resultado = audit.verificar_cadena()
    assert (resultado.primer_id_roto, resultado.motivo) == (4, "insertado")


def test_insertar_uno_sin_hash(bitacora):
    from custodia.core import audit

    _llenar(3)
    _sql(bitacora, "INSERT INTO eventos (momento, usuario, accion, exito) "
                   "VALUES ('t', 'falso', 'leer', 1)")

    resultado = audit.verificar_cadena()
    assert (resultado.primer_id_roto, resultado.motivo) == (4, "insertado")


def test_insertar_con_hash_propio_correcto_pero_mal_enlazado(bitacora):
    from custodia.core import audit

    _llenar(3)
    falso = audit._hash_registro(4, "t", "falso", "leer", None, 1, None, "a" * 64)
    _sql(bitacora,
         "INSERT INTO eventos (momento, usuario, accion, exito, hash_anterior, hash) "
         "VALUES ('t', 'falso', 'leer', 1, ?, ?)", "a" * 64, falso)

    resultado = audit.verificar_cadena()
    assert (resultado.primer_id_roto, resultado.motivo) == (4, "insertado")


def test_base_ilegible(tmp_path):
    from custodia.core import audit

    dañada = tmp_path / "no-es-sqlite.db"
    dañada.write_bytes(b"esto no es una base de datos" * 100)

    resultado = audit.verificar_cadena(dañada)
    assert not resultado.ok and resultado.motivo == "ilegible"


# ---------------------------------------------------------------------------
# Migración
# ---------------------------------------------------------------------------

def _base_vieja(ruta, ids=(1, 2, 3)) -> None:
    conn = sqlite3.connect(str(ruta))
    conn.execute("""CREATE TABLE eventos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, momento TEXT NOT NULL, usuario TEXT NOT NULL,
        accion TEXT NOT NULL, ruta TEXT, exito INTEGER NOT NULL, detalle TEXT)""")
    for i in ids:
        conn.execute("INSERT INTO eventos (id, momento, usuario, accion, ruta, exito, detalle) "
                     "VALUES (?, 't', 'ana', 'leer', NULL, 1, ?)", (i, f"viejo {i}"))
    conn.commit()
    conn.close()


@pytest.fixture
def vieja(tmp_path):
    from custodia.core import audit

    ruta = tmp_path / "vieja.db"
    yield ruta
    audit.close()


def test_migrar_una_base_vieja(vieja):
    from custodia.core import audit

    _base_vieja(vieja)
    audit.init(vieja)
    _llenar(2)

    resultado = audit.verificar_cadena()
    assert resultado.ok and resultado.total == 6
    iniciada = audit.consultar(accion="cadena_iniciada")
    assert len(iniciada) == 1 and iniciada[0]["detalle"] == "cadena desde id 1"
    assert audit.consultar(usuario="ana", limite=10)[-1]["detalle"] == "viejo 1"


def test_migrar_dos_veces_no_repite(vieja):
    from custodia.core import audit

    _base_vieja(vieja)
    audit.init(vieja)
    audit.init(vieja)

    assert len(audit.consultar(accion="cadena_iniciada")) == 1
    assert audit.verificar_cadena().ok


def test_los_huecos_anteriores_a_la_migracion_no_cuentan(vieja):
    from custodia.core import audit

    _base_vieja(vieja, ids=(5, 6, 9))
    audit.init(vieja)
    _llenar(2)

    resultado = audit.verificar_cadena()
    assert resultado.ok
    assert audit.consultar(accion="cadena_iniciada")[0]["detalle"] == "cadena desde id 5"


def test_tras_migrar_se_detecta_un_borrado_antiguo(vieja):
    from custodia.core import audit

    _base_vieja(vieja, ids=(5, 6, 9))
    audit.init(vieja)
    audit.flush()
    _sql(vieja, "DELETE FROM eventos WHERE id = 6")

    assert not audit.verificar_cadena().ok


def test_migrar_una_base_vacia(vieja):
    from custodia.core import audit

    _base_vieja(vieja, ids=())
    audit.init(vieja)

    assert audit.verificar_cadena().ok
    assert audit.consultar(accion="cadena_iniciada")[0]["detalle"] == "cadena desde id 1"


# ---------------------------------------------------------------------------
# Concurrencia
# ---------------------------------------------------------------------------

def test_varios_hilos_registrando_a_la_vez(bitacora):
    from custodia.core import audit

    def trabajo(n: int) -> None:
        for i in range(50):
            audit.registrar(f"hilo{n}", "leer", f"/{i}")

    hilos = [threading.Thread(target=trabajo, args=(n,)) for n in range(8)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    audit.flush()

    resultado = audit.verificar_cadena()
    assert resultado.ok and resultado.total == 400


def test_cerrar_con_la_cola_llena_no_tumba_el_proceso(tmp_path, monkeypatch):
    """El escritor se queda con su conexión hasta vaciar la cola."""
    from custodia.core import audit

    monkeypatch.setattr(audit, "_ESPERA_AL_CERRAR", 0.0)
    ruta = tmp_path / "saturada.db"
    audit.init(ruta)
    hilo = audit._hilo
    for i in range(300):
        audit.registrar("ana", "leer", f"/{i}")

    audit.close()

    assert audit._conn is None
    hilo.join(timeout=60)
    assert not hilo.is_alive()
    assert audit.verificar_cadena(ruta).total == 300


def test_verificar_mientras_otros_escriben(bitacora):
    from custodia.core import audit

    seguir = threading.Event()

    def escribir() -> None:
        while not seguir.wait(0.002):
            audit.registrar("ana", "leer", "/x")

    hilo = threading.Thread(target=escribir)
    hilo.start()
    try:
        for _ in range(5):
            resultado = audit.verificar_cadena()
            assert resultado.ok, resultado
    finally:
        seguir.set()
        hilo.join()


# ---------------------------------------------------------------------------
# Anclas
# ---------------------------------------------------------------------------

def test_se_ancla_cada_50_eventos_y_al_cerrar(bitacora, anclas):
    from custodia.core import audit

    _llenar(120)
    assert [a[0] for a in anclas] == [50, 100]
    assert anclas[0][1] == _fila(bitacora, 50)[1]

    audit.close()
    assert [a[0] for a in anclas] == [50, 100, 120]


def test_al_cerrar_no_se_repite_el_ancla_recien_escrita(bitacora, anclas):
    from custodia.core import audit

    _llenar(50)
    audit.close()
    assert [a[0] for a in anclas] == [50]


def test_coincide_con_las_anclas(bitacora, anclas):
    from custodia.core import audit

    _llenar(60)
    resultado = audit.verificar_cadena()
    assert resultado.ok and resultado.ultima_ancla == 50


def test_borrar_los_ultimos_se_detecta_por_el_ancla(bitacora, anclas):
    """La cadena restante es válida: solo el ancla delata lo que falta."""
    from custodia.core import audit

    _llenar(60)
    _sql(bitacora, "DELETE FROM eventos WHERE id > 40")

    resultado = audit.verificar_cadena()
    assert not resultado.ok
    assert (resultado.primer_id_roto, resultado.motivo) == (41, "truncado")
    assert resultado.ultima_ancla == 50


def test_un_recalculo_completo_deja_diferencia_con_el_ancla(bitacora, anclas):
    from custodia.core import audit

    _llenar(60)
    _sql(bitacora, "UPDATE eventos SET usuario = 'otro' WHERE id = 10")
    _recalcular(bitacora)

    resultado = audit.verificar_cadena()
    assert not resultado.ok
    assert (resultado.primer_id_roto, resultado.motivo) == (50, "ancla_distinta")


def test_un_recalculo_sin_anclas_no_se_detecta(bitacora):
    """El límite que el README declara: sin anclas, la cadena sola no basta."""
    from custodia.core import audit

    _llenar(10)
    _sql(bitacora, "UPDATE eventos SET usuario = 'otro' WHERE id = 5")
    _recalcular(bitacora)

    assert audit.verificar_cadena().ok


def test_una_ancla_vieja_no_se_tapa_con_otra_posterior(bitacora, anclas):
    """Truncar y reiniciar la numeración no debe esconder el ancla más alta."""
    from custodia.core import audit

    _llenar(60)
    _sql(bitacora, "DELETE FROM eventos WHERE id > 20")
    _sql(bitacora, "UPDATE sqlite_sequence SET seq = 20 WHERE name = 'eventos'")
    anclas.append((20, _fila(bitacora, 20)[1]))

    resultado = audit.verificar_cadena()
    assert (resultado.primer_id_roto, resultado.motivo) == (21, "truncado")


def test_sin_anclas_avisa_pero_no_falla(bitacora, anclas):
    from custodia.core import audit

    _llenar(3)
    resultado = audit.verificar_cadena()
    assert resultado.ok and "no tiene anclas" in resultado.aviso


def test_visor_inaccesible_avisa(bitacora, anclas, monkeypatch):
    from custodia.core import audit

    def falla(ruta):
        raise OSError("sin acceso")

    monkeypatch.setattr(audit, "_leer_anclas", falla)
    _llenar(3)
    resultado = audit.verificar_cadena()
    assert resultado.ok and "No se pudo leer" in resultado.aviso


def test_un_fallo_del_visor_no_impide_registrar(bitacora, monkeypatch):
    from custodia.core import audit, config

    def falla(ruta, id_, hash_):
        raise OSError("sin acceso")

    monkeypatch.setattr(config, "ANCLAR_BITACORA", True)
    monkeypatch.setattr(audit, "_emitir_ancla", falla)
    monkeypatch.setattr(audit, "_leer_anclas", lambda ruta: [])
    _llenar(55)

    assert audit.verificar_cadena().total == 55


def test_ancla_real_en_el_visor_de_eventos(tmp_path, monkeypatch):
    """De punta a punta con el Visor de eventos del equipo."""
    from custodia.core import audit, config

    monkeypatch.setattr(config, "ANCLAR_BITACORA", True)
    ruta = tmp_path / "real.db"
    audit.init(ruta)
    try:
        audit.registrar("ana", "leer", "/x")
        audit.flush()
        audit.close()

        try:
            anclas = audit._leer_anclas(ruta)
        except Exception as exc:
            pytest.skip(f"No se puede leer el Visor de eventos: {exc}")
        if not anclas:
            pytest.skip("Este equipo no permitió escribir en el Visor de eventos")

        assert anclas[0][0] == 1 and audit.verificar_cadena(ruta).ultima_ancla == 1
        _sql(ruta, "DELETE FROM eventos")
        resultado = audit.verificar_cadena(ruta)
        assert (resultado.primer_id_roto, resultado.motivo) == (1, "truncado")
    finally:
        audit.close()


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

def test_solo_un_administrador_verifica(bitacora):
    from custodia.core import audit
    from custodia.gui.sesion import Sesion

    with pytest.raises(PermissionError):
        Sesion(username="juan", token=None, es_admin=False).verificar_bitacora()

    audit.flush()
    denegado = audit.consultar(accion="verificar_bitacora")[0]
    assert not denegado["exito"] and denegado["usuario"] == "juan"


def test_la_verificacion_queda_en_la_bitacora(bitacora):
    from custodia.core import audit
    from custodia.gui.sesion import Sesion

    _llenar(3)
    sesion = Sesion(username="ana", token=None, es_admin=True)

    assert sesion.verificar_bitacora().ok
    audit.flush()
    evento = audit.consultar(accion="verificar_bitacora")[0]
    assert evento["exito"] and evento["detalle"] == "3 registros íntegros"
    assert audit.verificar_cadena().ok


def test_una_verificacion_fallida_queda_como_fallo(bitacora):
    from custodia.core import audit
    from custodia.gui.sesion import Sesion

    _llenar(3)
    _sql(bitacora, "UPDATE eventos SET detalle = 'x' WHERE id = 2")

    assert not Sesion(username="ana", token=None, es_admin=True).verificar_bitacora().ok
    audit.flush()
    evento = audit.consultar(accion="verificar_bitacora")[0]
    assert not evento["exito"] and evento["detalle"] == "rota en id 2: editado"
