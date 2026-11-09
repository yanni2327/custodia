# -*- coding: utf-8 -*-
"""
Autenticación contra Windows y sesiones en memoria.

Cada sesión guarda un token real del kernel: las pruebas comprueban que sirve
para suplantar mientras la sesión vive y que se libera cuando termina.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


def _envejecer(sesion, minutos: int) -> None:
    sesion.last_seen = datetime.now(timezone.utc) - timedelta(minutes=minutos)


@pytest.fixture
def almacen():
    from custodia.core import auth

    store = auth.SessionStore()
    yield store
    for sid in list(store._sessions):
        store.close(sid)


@requiere_admin
def test_una_sesion_guarda_un_token_que_suplanta(raiz, usuario_prueba, almacen):
    from custodia.core.impersonate import current_identity, impersonate

    cuenta, password = usuario_prueba
    sesion = almacen.create(cuenta.username, password)

    assert almacen.get(sesion.id) is sesion
    assert len(almacen) == 1
    with impersonate(sesion.token):
        assert current_identity().lower() == cuenta.username.lower()


@requiere_admin
def test_credenciales_malas_no_abren_sesion(raiz, usuario_prueba, almacen):
    from custodia.core.errors import AuthenticationError

    cuenta, _ = usuario_prueba
    with pytest.raises(AuthenticationError):
        almacen.create(cuenta.username, "ContraseñaEquivocada!123")
    assert len(almacen) == 0


@requiere_admin
def test_el_token_no_aparece_en_la_representacion(raiz, usuario_prueba, almacen):
    cuenta, password = usuario_prueba
    sesion = almacen.create(cuenta.username, password)
    assert "token" not in repr(sesion)


def test_sesion_inexistente(almacen):
    from custodia.core.errors import SessionError

    with pytest.raises(SessionError, match="inválida"):
        almacen.get("no-existe")


@requiere_admin
def test_cerrar_invalida_la_sesion_y_libera_el_token(raiz, usuario_prueba, almacen):
    from custodia.core.errors import SessionError

    cuenta, password = usuario_prueba
    sesion = almacen.create(cuenta.username, password)

    almacen.close(sesion.id)

    with pytest.raises(SessionError):
        almacen.get(sesion.id)
    assert int(sesion.token) == 0, "el handle del kernel sigue abierto"
    almacen.close(sesion.id)  # cerrar dos veces no es un error


@requiere_admin
def test_una_sesion_inactiva_expira(raiz, usuario_prueba, almacen):
    from custodia.core import config
    from custodia.core.errors import SessionError

    cuenta, password = usuario_prueba
    sesion = almacen.create(cuenta.username, password)
    _envejecer(sesion, config.SESSION_IDLE_MINUTES + 1)

    with pytest.raises(SessionError, match="inactividad"):
        almacen.get(sesion.id)
    assert len(almacen) == 0
    assert int(sesion.token) == 0


@requiere_admin
def test_usar_la_sesion_renueva_su_actividad(raiz, usuario_prueba, almacen):
    from custodia.core import config

    cuenta, password = usuario_prueba
    sesion = almacen.create(cuenta.username, password)
    _envejecer(sesion, config.SESSION_IDLE_MINUTES - 1)

    almacen.get(sesion.id)

    assert not sesion.is_idle(1)


@requiere_admin
def test_sweep_solo_cierra_las_inactivas(raiz, usuario_prueba, almacen):
    from custodia.core import config

    cuenta, password = usuario_prueba
    activa = almacen.create(cuenta.username, password)
    inactiva = almacen.create(cuenta.username, password)
    _envejecer(inactiva, config.SESSION_IDLE_MINUTES + 1)

    assert almacen.sweep() == 1
    assert almacen.get(activa.id) is activa
    assert len(almacen) == 1


@requiere_admin
def test_cuenta_deshabilitada(raiz, usuario_prueba):
    import win32net
    import win32netcon
    from custodia.core import auth
    from custodia.core.errors import AuthenticationError

    cuenta, password = usuario_prueba
    flags = win32net.NetUserGetInfo(None, cuenta.username, 1)["flags"]
    win32net.NetUserSetInfo(None, cuenta.username, 1008,
                            {"flags": flags | win32netcon.UF_ACCOUNTDISABLE})

    with pytest.raises(AuthenticationError, match="deshabilitada"):
        auth.logon(cuenta.username, password)


@requiere_admin
def test_no_se_puede_enumerar_cuentas_por_el_mensaje(raiz, usuario_prueba):
    from custodia.core import auth
    from custodia.core.errors import AuthenticationError

    cuenta, _ = usuario_prueba
    with pytest.raises(AuthenticationError) as contrasena_mala:
        auth.logon(cuenta.username, "ContraseñaEquivocada!123")
    with pytest.raises(AuthenticationError) as usuario_inexistente:
        auth.logon("no_existe_jamas_xyz", "ContraseñaEquivocada!123")

    assert str(contrasena_mala.value) == str(usuario_inexistente.value)
