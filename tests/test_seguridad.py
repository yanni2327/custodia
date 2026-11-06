# -*- coding: utf-8 -*-
"""
Pruebas del bloqueo por fuerza bruta.

Se aísla del sistema: el registro de intentos se redirige a un archivo
temporal, y la protección por ACL y la bitácora se sustituyen por funciones
vacías. Así la lógica de conteo y bloqueo se prueba sin privilegios ni Windows.
"""
from __future__ import annotations

import pytest

from custodia.core import config, seguridad


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INTENTOS_FILE", tmp_path / "intentos.dat")
    monkeypatch.setattr(config, "MAX_INTENTOS", 3)
    monkeypatch.setattr(config, "VENTANA_INTENTOS_MIN", 10)
    monkeypatch.setattr(config, "BLOQUEO_MIN", 15)
    monkeypatch.setattr(seguridad.crypto, "proteger_solo_admin", lambda ruta: None)
    monkeypatch.setattr(seguridad.audit, "registrar", lambda *a, **k: None)
    yield


def test_no_bloquea_antes_del_umbral(aislado):
    assert seguridad.esta_bloqueado("ana") == (False, 0)
    for _ in range(2):          # dos fallos, umbral es 3
        bloqueado, _ = seguridad.registrar_fallo("ana")
        assert not bloqueado
    assert seguridad.esta_bloqueado("ana")[0] is False


def test_bloquea_al_alcanzar_el_umbral(aislado):
    for _ in range(2):
        seguridad.registrar_fallo("ana")
    bloqueado, restante = seguridad.registrar_fallo("ana")   # tercero
    assert bloqueado and restante > 0
    esta, falta = seguridad.esta_bloqueado("ana")
    assert esta and falta > 0


def test_el_bloqueo_es_por_cuenta(aislado):
    for _ in range(3):
        seguridad.registrar_fallo("ana")
    assert seguridad.esta_bloqueado("ana")[0]
    assert seguridad.esta_bloqueado("jefe")[0] is False


def test_limpiar_borra_el_historial(aislado):
    for _ in range(3):
        seguridad.registrar_fallo("ana")
    assert seguridad.esta_bloqueado("ana")[0]
    seguridad.limpiar("ana")
    assert seguridad.esta_bloqueado("ana") == (False, 0)


def test_mayusculas_no_evaden_el_bloqueo(aislado):
    for _ in range(3):
        seguridad.registrar_fallo("Ana")
    # El mismo usuario con otra caja no es una cuenta distinta.
    assert seguridad.esta_bloqueado("ana")[0]
