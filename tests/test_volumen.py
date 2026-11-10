# -*- coding: utf-8 -*-
"""
Verificación de BitLocker (C15).

La consulta a WMI se simula para recorrer los estados y las dos opciones; una
prueba final la hace de verdad.
"""
from __future__ import annotations

import pytest

from conftest import pytestmark  # noqa: F401

from custodia.core import audit, config, volumen


@pytest.fixture(autouse=True)
def sin_estado_previo(monkeypatch):
    monkeypatch.setattr(volumen, "_ultima", None)


def _wmi(monkeypatch, valor) -> None:
    def consulta(unidad):
        if isinstance(valor, Exception):
            raise valor
        return valor

    monkeypatch.setattr(volumen, "_proteccion_wmi", consulta)


def _eventos() -> list[dict]:
    audit.flush()
    return audit.consultar(accion="volumen_sin_proteger")


@pytest.mark.parametrize("valor, esperado", [
    (1, "protegido"), (0, "sin_proteger"), (2, "desconocido"), (None, "desconocido"),
])
def test_estado_segun_protection_status(monkeypatch, valor, esperado):
    _wmi(monkeypatch, valor)
    assert volumen.estado_bitlocker(r"C:\ProgramData\Custodia\storage") == esperado


def test_un_fallo_de_wmi_no_lanza(monkeypatch):
    _wmi(monkeypatch, PermissionError("acceso denegado"))
    assert volumen.estado_bitlocker(r"C:\x") == "desconocido"


def test_una_ruta_de_red_es_desconocida(monkeypatch):
    def nunca(unidad):
        raise AssertionError("no debe consultar WMI")

    monkeypatch.setattr(volumen, "_proteccion_wmi", nunca)
    assert volumen.estado_bitlocker(r"\\servidor\recurso\almacen") == "desconocido"


def test_consulta_la_unidad_del_almacen(monkeypatch):
    vistas = []
    monkeypatch.setattr(volumen, "_proteccion_wmi", lambda u: vistas.append(u) or 1)

    volumen.estado_bitlocker(r"d:\datos\almacen")

    assert vistas == ["D:"]


@pytest.mark.parametrize("exigir", [False, True])
@pytest.mark.parametrize("valor, estado, bloquea_si_exige", [
    (1, "protegido", False), (0, "sin_proteger", True), (None, "desconocido", False),
])
def test_arranque_estados_por_opcion(bitacora, monkeypatch, exigir, valor, estado,
                                     bloquea_si_exige):
    monkeypatch.setattr(config, "EXIGIR_BITLOCKER", exigir)
    _wmi(monkeypatch, valor)

    evaluacion = volumen.evaluar_arranque(r"C:\almacen")

    assert evaluacion.estado == estado
    assert evaluacion.bloquear is (exigir and bloquea_si_exige)
    assert volumen.ultima_evaluacion() is evaluacion


@pytest.mark.parametrize("exigir", [False, True])
def test_sin_proteger_queda_en_la_bitacora_y_dice_que_hacer(bitacora, monkeypatch, exigir):
    monkeypatch.setattr(config, "EXIGIR_BITLOCKER", exigir)
    _wmi(monkeypatch, 0)

    evaluacion = volumen.evaluar_arranque(r"C:\almacen")

    evento, = _eventos()
    assert evento["exito"] is False and evento["detalle"] == "unidad C:"
    assert "C:" in evaluacion.mensaje and "BitLocker" in evaluacion.mensaje


@pytest.mark.parametrize("valor", [1, None])
def test_los_demas_estados_no_generan_evento_ni_aviso(bitacora, monkeypatch, valor):
    _wmi(monkeypatch, valor)

    evaluacion = volumen.evaluar_arranque(r"C:\almacen")

    assert _eventos() == [] and evaluacion.mensaje == ""


def test_por_defecto_no_se_exige():
    assert config.EXIGIR_BITLOCKER is False


def test_usa_el_almacen_configurado(bitacora, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "STORAGE_ROOT", tmp_path)
    vistas = []
    monkeypatch.setattr(volumen, "_proteccion_wmi", lambda u: vistas.append(u) or 1)

    volumen.evaluar_arranque()

    assert vistas == [tmp_path.drive.upper()]


def test_solo_el_administrador_ve_el_estado(bitacora, monkeypatch):
    from custodia.gui.sesion import Sesion

    _wmi(monkeypatch, 0)
    volumen.evaluar_arranque(r"C:\almacen")

    assert Sesion(username="juan", token=None, es_admin=False).estado_volumen() is None
    estado, aviso = Sesion(username="ana", token=None, es_admin=True).estado_volumen()
    assert estado == "sin_proteger" and "BitLocker" in aviso


def test_sin_comprobacion_previa_no_hay_estado():
    from custodia.gui.sesion import Sesion

    assert Sesion(username="ana", token=None, es_admin=True).estado_volumen() is None


def test_consulta_real_a_wmi(tmp_path):
    """Sin simular. Se omite si este equipo no permite consultar BitLocker."""
    unidad = volumen._unidad_de(tmp_path)
    try:
        valor = volumen._proteccion_wmi(unidad)
    except Exception as exc:
        pytest.skip(f"No se puede consultar BitLocker aquí: {exc}")
    if valor is None:
        pytest.skip("WMI no conoce esta unidad")

    assert volumen.estado_bitlocker(tmp_path) in ("protegido", "sin_proteger", "desconocido")
    assert isinstance(valor, int)
