# -*- coding: utf-8 -*-
"""
Salvaguardas al sacar cuentas de grupos y eliminar grupos desde la interfaz.

Lo que se protege es no dejar la aplicación sin nadie que la administre:
nadie se saca a sí mismo de los administradores y nunca se saca al último.
No tocan Windows: se sustituye el módulo de cuentas.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from custodia.core import config
from custodia.gui import sesion as modulo_sesion
from custodia.gui.sesion import Sesion


@pytest.fixture
def cuentas(monkeypatch):
    estado = {"admins": ["ana", "juan"], "quitados": [], "eliminados": [], "bitacora": []}
    monkeypatch.setattr(modulo_sesion.accounts, "listar_usuarios", lambda: [
        SimpleNamespace(username=u, es_admin=u in estado["admins"])
        for u in ("ana", "juan", "marta")
    ])
    monkeypatch.setattr(modulo_sesion.accounts, "quitar_de_grupo",
                        lambda g, u: estado["quitados"].append((g, u)))
    monkeypatch.setattr(modulo_sesion.accounts, "eliminar_grupo",
                        lambda n: estado["eliminados"].append(n))
    monkeypatch.setattr(modulo_sesion.audit, "registrar",
                        lambda *a, **k: estado["bitacora"].append((a, k)))
    return estado


def _admin(nombre="ana") -> Sesion:
    return Sesion(username=nombre, token=None, es_admin=True)


def test_quitar_de_un_grupo_normal(cuentas):
    _admin().quitar_de_grupo("Contabilidad", "marta")
    assert cuentas["quitados"] == [("Contabilidad", "marta")]
    (args, kwargs), = cuentas["bitacora"]
    assert args[1] == "quitar_grupo" and kwargs["detalle"] == "marta <- Contabilidad"


def test_otro_admin_puede_sacar_a_un_admin(cuentas):
    _admin("ana").quitar_de_grupo(config.ADMIN_GROUP, "juan")
    assert cuentas["quitados"] == [(config.ADMIN_GROUP, "juan")]


def test_nadie_se_saca_a_si_mismo_de_administradores(cuentas):
    with pytest.raises(PermissionError):
        _admin("ana").quitar_de_grupo(config.ADMIN_GROUP, "ANA")
    assert cuentas["quitados"] == []


def test_nunca_se_saca_al_ultimo_administrador(cuentas):
    cuentas["admins"] = ["juan"]          # ana gestiona, pero juan es el único admin
    with pytest.raises(PermissionError):
        _admin("ana").quitar_de_grupo(config.ADMIN_GROUP, "juan")
    assert cuentas["quitados"] == []


def test_sin_ser_admin_no_se_toca_ningun_grupo(cuentas):
    usuario = Sesion(username="marta", token=None, es_admin=False)
    with pytest.raises(PermissionError):
        usuario.quitar_de_grupo("Contabilidad", "juan")
    with pytest.raises(PermissionError):
        usuario.eliminar_grupo("Contabilidad")
    assert cuentas["quitados"] == [] and cuentas["eliminados"] == []


def test_retirar_una_cuenta_y_queda_en_la_bitacora(cuentas, monkeypatch):
    retiradas = []
    monkeypatch.setattr(modulo_sesion.accounts, "retirar_de_custodia", retiradas.append)
    _admin().retirar_usuario("marta")
    assert retiradas == ["marta"]
    (args, kwargs), = cuentas["bitacora"]
    assert args[1] == "retirar_usuario" and kwargs["detalle"] == "marta"


def test_nadie_se_retira_a_si_mismo_ni_al_ultimo_admin(cuentas, monkeypatch):
    retiradas = []
    monkeypatch.setattr(modulo_sesion.accounts, "retirar_de_custodia", retiradas.append)
    with pytest.raises(PermissionError):
        _admin("ana").retirar_usuario("ana")
    cuentas["admins"] = ["juan"]
    with pytest.raises(PermissionError):
        _admin("ana").retirar_usuario("juan")
    assert retiradas == []


def test_incorporar_exige_admin_y_queda_en_la_bitacora(cuentas, monkeypatch):
    incorporadas = []
    monkeypatch.setattr(modulo_sesion.accounts, "incorporar_usuario",
                        lambda u, es_admin=False: incorporadas.append((u, es_admin)))
    with pytest.raises(PermissionError):
        Sesion(username="marta", token=None, es_admin=False).incorporar_usuario("dioya")
    _admin().incorporar_usuario("dioya", es_admin=True)
    assert incorporadas == [("dioya", True)]
    (args, kwargs), = cuentas["bitacora"]
    assert args[1] == "incorporar_usuario" and kwargs["detalle"] == "dioya (administrador)"


def test_eliminar_grupo_queda_en_la_bitacora(cuentas):
    _admin().eliminar_grupo("Contabilidad")
    assert cuentas["eliminados"] == ["Contabilidad"]
    (args, kwargs), = cuentas["bitacora"]
    assert args[1] == "eliminar_grupo" and kwargs["detalle"] == "Contabilidad"
