# -*- coding: utf-8 -*-
"""
Restablecer y cambiar contraseñas.

- Un administrador pone una contraseña temporal a otra cuenta y Windows obliga
  a cambiarla en el primer inicio de sesión (error 1907 de LogonUser).
- Cada persona puede cambiar la suya conociendo la actual.

La prueba de integración usa una cuenta temporal real (la crea y la borra);
las demás no tocan Windows.
"""
from __future__ import annotations

import re

import pytest

from conftest import requiere_admin
from custodia.core import accounts, auth
from custodia.core.errors import (AccountError, AuthenticationError,
                                  CambioDeContrasenaRequerido)
from custodia.gui import sesion as modulo_sesion
from custodia.gui.sesion import Sesion


# -- contraseña temporal y regla mínima -------------------------------------

def test_la_temporal_es_legible_y_variada():
    vistas = set()
    for _ in range(50):
        t = accounts.contrasena_temporal()
        assert re.fullmatch(r"[A-Za-z2-9]{4}-[A-Za-z2-9]{4}-[A-Za-z2-9]{4}", t)
        assert not set("0O1lI") & set(t)            # nada que se confunda
        assert accounts.regla_contrasena(t) is None  # cumple la regla de Custodia
        vistas.add(t)
    assert len(vistas) == 50                         # aleatoria de verdad


@pytest.mark.parametrize("nueva, valida", [
    ("abc", False), ("abcdefgh", False), ("12345678", False),
    ("abcd1234", True), ("Frase larga 2026", True),
])
def test_regla_minima(nueva, valida):
    assert (accounts.regla_contrasena(nueva) is None) == valida


# -- reglas de la sesión (sin Windows) ----------------------------------------

@pytest.fixture
def falsos(monkeypatch):
    estado = {"bitacora": [], "cambios": [], "forzadas": [], "limpias": []}
    m = modulo_sesion
    monkeypatch.setattr(m.accounts, "cambiar_password",
                        lambda u, p: estado["cambios"].append((u, p)))
    monkeypatch.setattr(m.accounts, "forzar_cambio_de_contrasena",
                        lambda u: estado["forzadas"].append(u))
    monkeypatch.setattr(m.seguridad, "limpiar", lambda u: estado["limpias"].append(u))
    monkeypatch.setattr(m.audit, "registrar",
                        lambda *a, **k: estado["bitacora"].append((a, k)))
    return estado


def test_admin_restablece_y_la_temporal_no_queda_en_la_bitacora(falsos):
    temporal = Sesion(username="ana", token=None, es_admin=True).restablecer_contrasena("juan")
    assert falsos["cambios"] == [("juan", temporal)]
    assert falsos["forzadas"] == ["juan"]      # Windows exigirá cambiarla
    assert falsos["limpias"] == ["juan"]       # y se le quita el bloqueo
    (args, kwargs), = falsos["bitacora"]
    assert args[1] == "restablecer_contrasena" and kwargs["detalle"] == "juan"
    assert temporal not in repr(falsos["bitacora"])


def test_restablecer_no_vale_para_si_mismo_ni_sin_ser_admin(falsos):
    with pytest.raises(PermissionError):
        Sesion(username="ana", token=None, es_admin=True).restablecer_contrasena("Ana")
    with pytest.raises(PermissionError):
        Sesion(username="juan", token=None, es_admin=False).restablecer_contrasena("ana")
    assert falsos["cambios"] == []


def test_la_nueva_debe_cumplir_la_regla_y_ser_distinta(falsos):
    s = Sesion(username="ana", token=None, es_admin=False)
    with pytest.raises(AccountError):
        s.cambiar_mi_contrasena("Actual.2026", "abc")
    with pytest.raises(AccountError):
        s.cambiar_mi_contrasena("Actual2026", "Actual2026")


def test_al_entrar_con_temporal_se_pide_cambiarla(monkeypatch, falsos):
    def logon(u, p):
        raise CambioDeContrasenaRequerido()
    monkeypatch.setattr(modulo_sesion.seguridad, "esta_bloqueado", lambda u: (False, 0))
    monkeypatch.setattr(modulo_sesion.auth, "logon", logon)
    monkeypatch.setattr(modulo_sesion.accounts, "es_miembro_app", lambda u: u == "ana")
    with pytest.raises(CambioDeContrasenaRequerido):
        Sesion.iniciar("ana", "Kp7x-mR4q-Wn9c")
    # Una cuenta ajena a Custodia no llega ni a que se le ofrezca el cambio.
    with pytest.raises(AuthenticationError, match="no tiene acceso a Custodia"):
        Sesion.iniciar("dioya", "lo-que-sea")


# -- ciclo completo con una cuenta real de Windows ---------------------------

@requiere_admin
def test_ciclo_completo_con_windows(usuario_prueba):
    cuenta, password = usuario_prueba
    temporal = accounts.contrasena_temporal()
    accounts.cambiar_password(cuenta.username, temporal)
    accounts.forzar_cambio_de_contrasena(cuenta.username)

    # Windows no deja entrar con la temporal sin cambiarla…
    with pytest.raises(CambioDeContrasenaRequerido):
        auth.logon(cuenta.username, temporal)
    # …ni cambiarla sin conocerla…
    with pytest.raises(AuthenticationError):
        accounts.cambiar_password_propia(cuenta.username, "no-es-la-temporal", "Nueva.2026xyz")
    # …y con la temporal correcta, se cambia y se entra con la nueva.
    accounts.cambiar_password_propia(cuenta.username, temporal, "Nueva.2026xyz")
    auth.logon(cuenta.username, "Nueva.2026xyz").Close()
    with pytest.raises(AuthenticationError):
        auth.logon(cuenta.username, temporal)

    # La cuenta vuelve a tener «la contraseña nunca expira», como al crearla.
    import win32net
    import win32netcon
    flags = win32net.NetUserGetInfo(None, cuenta.username, 1)["flags"]
    assert flags & win32netcon.UF_DONT_EXPIRE_PASSWD
