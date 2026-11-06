# -*- coding: utf-8 -*-
"""
Pruebas de la protección de descargas: clave de descarga y límite anti-masiva.

Se aísla del sistema (archivo temporal, ACL y bitácora sustituidas por vacías),
así que la lógica se prueba sin privilegios ni Windows.
"""
from __future__ import annotations

import pytest

from custodia.core import config, descargas


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DESCARGAS_FILE", tmp_path / "descargas.dat")
    monkeypatch.setattr(config, "MAX_DESCARGAS", 3)
    monkeypatch.setattr(config, "VENTANA_DESCARGAS_MIN", 10)
    monkeypatch.setattr(config, "BLOQUEO_DESCARGAS_MIN", 15)
    monkeypatch.setattr(descargas.crypto, "proteger_solo_admin", lambda ruta: None)
    monkeypatch.setattr(descargas.audit, "registrar", lambda *a, **k: None)
    yield


def test_clave_de_descarga(aislado):
    assert not descargas.tiene_clave("ana")
    descargas.establecer_clave("Ana", "secreto")
    assert descargas.tiene_clave("ana")
    assert descargas.verificar_clave("ana", "secreto")
    assert not descargas.verificar_clave("ana", "mala")
    assert not descargas.verificar_clave("bob", "lo-que-sea")


def test_la_clave_no_se_guarda_en_claro(aislado, tmp_path):
    descargas.establecer_clave("ana", "secreto-visible")
    contenido = (tmp_path / "descargas.dat").read_text("utf-8")
    assert "secreto-visible" not in contenido   # solo se guarda el hash


def test_quitar_clave(aislado):
    descargas.establecer_clave("ana", "xxxx")
    descargas.quitar_clave("ana")
    assert not descargas.tiene_clave("ana")
    assert not descargas.verificar_clave("ana", "xxxx")


def test_el_limite_bloquea_la_descarga_masiva(aislado):
    for _ in range(2):           # umbral es 3
        bloqueado, _ = descargas.registrar("ana")
        assert not bloqueado
    bloqueado, restante = descargas.registrar("ana")   # tercera
    assert bloqueado and restante > 0
    assert descargas.estado("ana")[0]


def test_el_limite_es_por_usuario(aislado):
    for _ in range(3):
        descargas.registrar("ana")
    assert descargas.estado("ana")[0]
    assert descargas.estado("bob")[0] is False
