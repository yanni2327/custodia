# -*- coding: utf-8 -*-
"""
Pruebas de cuentas de Windows, con foco en las salvaguardas.

Las pruebas que más importan aquí no son las que comprueban que crear un
usuario funciona, sino las que comprueban que la aplicación se NIEGA a tocar
cuentas que no son suyas.
"""
from __future__ import annotations

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


@requiere_admin
def test_crear_usuario_lo_mete_en_el_grupo_de_la_app(usuario_prueba):
    from custodia.core import config

    cuenta, _ = usuario_prueba
    assert config.APP_GROUP in cuenta.grupos
    assert cuenta.sid.startswith("S-1-")


@requiere_admin
def test_no_se_puede_eliminar_al_administrador(grupos_app):
    """
    La salvaguarda más importante del proyecto. Sin ella, un bug en la interfaz
    de administración podría dejar la máquina sin cuenta de administrador.
    """
    from custodia.core import accounts
    from custodia.core.errors import ProtectedAccount

    for nombre in ("Administrator", "Administrador", "Guest"):
        with pytest.raises(ProtectedAccount):
            accounts.eliminar_usuario(nombre)


@requiere_admin
def test_no_se_puede_tocar_una_cuenta_ajena(grupos_app):
    """Una cuenta que existe pero no está en APP_GROUP no se administra."""
    import win32api
    from custodia.core import accounts
    from custodia.core.errors import AccountError, ProtectedAccount

    yo = win32api.GetUserName()
    with pytest.raises((ProtectedAccount, AccountError)):
        accounts.eliminar_usuario(yo)


@requiere_admin
def test_no_se_puede_eliminar_el_grupo_interno(grupos_app):
    from custodia.core import accounts, config
    from custodia.core.errors import ProtectedAccount

    with pytest.raises(ProtectedAccount):
        accounts.eliminar_grupo(config.APP_GROUP)


@requiere_admin
def test_no_se_puede_sacar_a_un_usuario_del_grupo_de_la_app(usuario_prueba):
    """Sacarlo lo dejaría huérfano: nadie volvería a reconocerlo como propio."""
    from custodia.core import accounts, config
    from custodia.core.errors import ProtectedAccount

    cuenta, _ = usuario_prueba
    with pytest.raises(ProtectedAccount):
        accounts.quitar_de_grupo(config.APP_GROUP, cuenta.username)


@requiere_admin
def test_usuario_duplicado(usuario_prueba):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    cuenta, password = usuario_prueba
    with pytest.raises(AccountError, match="ya existe"):
        accounts.crear_usuario(cuenta.username, password)


@requiere_admin
def test_password_debil_la_rechaza_windows(grupos_app):
    """
    No validamos complejidad en nuestro código: la política de la máquina es la
    autoridad. Si la máquina no exige complejidad, esta prueba se salta.
    """
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    try:
        accounts.crear_usuario("cust_t2", "abc")
    except AccountError:
        pass
    else:
        accounts.eliminar_usuario("cust_t2")
        pytest.skip("Esta máquina no exige complejidad de contraseña")


@requiere_admin
def test_nombre_demasiado_largo(grupos_app):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    with pytest.raises(AccountError, match="20 caracteres"):
        accounts.crear_usuario("un_nombre_absurdamente_largo", "Prueba.2026!SOP")


@requiere_admin
def test_listar_solo_devuelve_cuentas_de_la_app(usuario_prueba):
    from custodia.core import accounts

    cuenta, _ = usuario_prueba
    nombres = {c.username.lower() for c in accounts.listar_usuarios()}

    assert cuenta.username.lower() in nombres
    assert "administrator" not in nombres
    assert "administrador" not in nombres


@requiere_admin
def test_admin_de_la_app(grupos_app):
    from custodia.core import accounts

    nombre = "cust_adm"
    try:
        accounts.eliminar_usuario(nombre)
    except Exception:
        pass

    cuenta = accounts.crear_usuario(nombre, "Prueba.2026!SOP", es_admin=True)
    try:
        assert cuenta.es_admin
        assert accounts.es_admin(nombre)
    finally:
        accounts.eliminar_usuario(nombre)
