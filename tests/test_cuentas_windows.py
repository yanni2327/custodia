# -*- coding: utf-8 -*-
"""
Ciclo de vida de cuentas y grupos reales de Windows.

Complementa a `test_accounts`. La cuenta «externa» se crea directamente con la
API de Windows para representar una cuenta que ya existía antes de Custodia,
como la personal del dueño del equipo: es la que las salvaguardas protegen.

Todo lo creado aquí se borra al terminar, y el almacén se redirige a una
carpeta temporal.
"""
from __future__ import annotations

import pytest
import win32net
import win32netcon

from conftest import pytestmark, requiere_admin  # noqa: F401

CONTRASENA = "Prueba.2026!SOP"
EXTERNA = "cust_ext"
GRUPO = "cust_grp_t"


def _borrar_cuenta(nombre: str) -> None:
    try:
        win32net.NetUserDel(None, nombre)
    except Exception:
        pass


def _borrar_grupo(nombre: str) -> None:
    try:
        win32net.NetLocalGroupDel(None, nombre)
    except Exception:
        pass


def _existe(nombre: str) -> bool:
    try:
        win32net.NetUserGetInfo(None, nombre, 1)
    except Exception:
        return False
    return True


@pytest.fixture
def cuenta_externa(raiz, grupos_app):
    """Cuenta de Windows ajena a Custodia: sin grupos de la app ni marca."""
    _borrar_cuenta(EXTERNA)
    win32net.NetUserAdd(None, 1, {
        "name": EXTERNA,
        "password": CONTRASENA,
        "priv": win32netcon.USER_PRIV_USER,
        "home_dir": None,
        "comment": "Cuenta personal",
        "flags": win32netcon.UF_SCRIPT | win32netcon.UF_DONT_EXPIRE_PASSWD,
        "script_path": None,
    })
    yield EXTERNA
    _borrar_cuenta(EXTERNA)


@pytest.fixture
def grupo(grupos_app):
    from custodia.core import accounts

    _borrar_grupo(GRUPO)
    accounts.crear_grupo(GRUPO, "Grupo de prueba")
    yield GRUPO
    _borrar_grupo(GRUPO)


def _puede_entrar(nombre: str, password: str) -> bool:
    from custodia.core import auth
    from custodia.core.errors import AuthenticationError

    try:
        auth.logon(nombre, password).Close()
    except AuthenticationError:
        return False
    return True


# ---------------------------------------------------------------------------
# Consultas: ante la duda, se niega
# ---------------------------------------------------------------------------

@requiere_admin
def test_cuenta_inexistente_se_informa_y_no_pertenece(grupos_app):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    with pytest.raises(AccountError, match="no existe"):
        accounts.info_usuario("no_existe_jamas_xyz")
    with pytest.raises(AccountError, match="No se encontró"):
        accounts.sid_de("no_existe_jamas_xyz")
    assert accounts.es_miembro_app("no_existe_jamas_xyz") is False


@requiere_admin
def test_pertenencia_real(raiz, usuario_prueba, cuenta_externa):
    from custodia.core import accounts

    cuenta, _ = usuario_prueba
    assert accounts.es_miembro_app(cuenta.username)
    assert not accounts.es_miembro_app(cuenta_externa)
    assert not accounts.es_admin(cuenta.username)
    assert accounts.info_usuario(cuenta.username).creada_por_custodia
    assert not accounts.info_usuario(cuenta_externa).creada_por_custodia


@requiere_admin
def test_asegurar_grupos_es_idempotente(grupos_app):
    from custodia.core import accounts, config

    accounts.asegurar_grupos()

    nombres = {g["name"] for g in accounts.listar_grupos()}
    assert {config.APP_GROUP, config.ADMIN_GROUP} <= nombres


# ---------------------------------------------------------------------------
# Salvaguardas sobre cuentas ajenas
# ---------------------------------------------------------------------------

@requiere_admin
def test_una_cuenta_ajena_no_se_modifica(cuenta_externa, grupo):
    from custodia.core import accounts
    from custodia.core.errors import ProtectedAccount

    for intento in (
        lambda: accounts.cambiar_password(cuenta_externa, "Otra.2026!SOP"),
        lambda: accounts.eliminar_usuario(cuenta_externa),
        lambda: accounts.forzar_cambio_de_contrasena(cuenta_externa),
        lambda: accounts.retirar_de_custodia(cuenta_externa),
        lambda: accounts.añadir_a_grupo(grupo, cuenta_externa),
        lambda: accounts.quitar_de_grupo(grupo, cuenta_externa),
    ):
        with pytest.raises(ProtectedAccount):
            intento()

    assert _puede_entrar(cuenta_externa, CONTRASENA)


# ---------------------------------------------------------------------------
# Crear, cambiar y eliminar
# ---------------------------------------------------------------------------

@requiere_admin
def test_si_fallan_los_grupos_no_queda_cuenta_huerfana(raiz, grupos_app, monkeypatch):
    """Una cuenta sin grupo ninguna salvaguarda la reconocería después."""
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    def falla(grupo, usuario):
        raise AccountError("fallo al añadir al grupo")

    _borrar_cuenta("cust_huerf")
    monkeypatch.setattr(accounts, "_añadir_a_grupo", falla)
    try:
        with pytest.raises(AccountError, match="fallo al añadir"):
            accounts.crear_usuario("cust_huerf", CONTRASENA)
        assert not _existe("cust_huerf")
    finally:
        _borrar_cuenta("cust_huerf")


@requiere_admin
def test_cambiar_password_la_aplica_windows(raiz, usuario_prueba):
    from custodia.core import accounts

    cuenta, password = usuario_prueba
    accounts.cambiar_password(cuenta.username, "Nueva.2026!SOP")

    assert _puede_entrar(cuenta.username, "Nueva.2026!SOP")
    assert not _puede_entrar(cuenta.username, password)


@requiere_admin
def test_eliminar_borra_la_cuenta_de_windows(raiz, usuario_prueba):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    cuenta, password = usuario_prueba
    accounts.eliminar_usuario(cuenta.username)

    assert not _existe(cuenta.username)
    assert not _puede_entrar(cuenta.username, password)
    with pytest.raises(AccountError, match="no existe"):
        accounts.eliminar_usuario(cuenta.username)


@requiere_admin
def test_la_cuenta_nueva_recibe_su_espacio(raiz, usuario_prueba):
    from custodia.core import acl

    cuenta, _ = usuario_prueba
    carpeta = raiz / cuenta.username

    assert carpeta.is_dir()
    assert any(cuenta.username.lower() in e.principal.lower()
               for e in acl.leer_permisos(carpeta))


@requiere_admin
def test_la_cuenta_nueva_es_propietaria_de_su_espacio(raiz, usuario_prueba):
    """Lo que promete asegurar_espacio: nunca puede quedar excluida de su carpeta."""
    from custodia.core import acl

    cuenta, _ = usuario_prueba
    assert cuenta.username.lower() in acl.propietario(raiz / cuenta.username).lower()


def _restore_habilitado() -> bool:
    import win32api
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(),
                                           win32security.TOKEN_QUERY)
    try:
        luid = win32security.LookupPrivilegeValue(None, "SeRestorePrivilege")
        privilegios = win32security.GetTokenInformation(token, win32security.TokenPrivileges)
        return any(p == luid and a & win32security.SE_PRIVILEGE_ENABLED
                   for p, a in privilegios)
    finally:
        token.Close()


@requiere_admin
def test_el_privilegio_no_queda_habilitado(raiz, usuario_prueba):
    from custodia.core import acl

    cuenta, _ = usuario_prueba
    acl.cambiar_propietario(raiz / cuenta.username, cuenta.username)
    assert not _restore_habilitado()


@requiere_admin
def test_el_privilegio_se_deshabilita_aunque_falle(raiz, usuario_prueba):
    from custodia.core import acl

    cuenta, _ = usuario_prueba
    with pytest.raises(Exception):
        acl.cambiar_propietario(raiz / "no_existe", cuenta.username)
    assert not _restore_habilitado()


@requiere_admin
def test_si_no_se_asigna_el_propietario_se_informa_y_se_registra(raiz, usuario_prueba,
                                                                 bitacora, monkeypatch):
    from custodia.core import acl, audit, espacios
    from custodia.core.errors import AccountError, PermissionDenied

    cuenta, _ = usuario_prueba

    def falla(ruta, principal):
        raise PermissionDenied("Sin privilegios para cambiar el propietario")

    monkeypatch.setattr(acl, "cambiar_propietario", falla)

    with pytest.raises(AccountError, match="propietaria"):
        espacios.asegurar_espacio(cuenta.username)

    assert (raiz / cuenta.username).is_dir()
    audit.flush()
    fallo = audit.consultar(accion="propietario_espacio")[0]
    assert fallo["exito"] is False and "PermissionDenied" in fallo["detalle"]
    assert fallo["ruta"] == f"/{cuenta.username}"


@requiere_admin
def test_el_espacio_de_una_cuenta_inexistente_queda_para_administradores(raiz, grupos_app):
    from custodia.core import acl, espacios

    carpeta = espacios.asegurar_espacio("no_existe_jamas_xyz")

    assert carpeta.is_dir()
    assert "no_existe_jamas_xyz" not in acl.propietario(carpeta).lower()


# ---------------------------------------------------------------------------
# Incorporar y retirar cuentas existentes
# ---------------------------------------------------------------------------

@requiere_admin
def test_incorporables_solo_ofrece_cuentas_normales_de_fuera(raiz, usuario_prueba,
                                                             cuenta_externa):
    from custodia.core import accounts

    cuenta, _ = usuario_prueba
    nombres = {c["usuario"].lower() for c in accounts.cuentas_incorporables()}

    assert cuenta_externa in nombres
    assert cuenta.username.lower() not in nombres
    assert not nombres & {"administrator", "administrador", "guest", "invitado"}


@requiere_admin
def test_una_cuenta_deshabilitada_no_es_incorporable(cuenta_externa):
    from custodia.core import accounts

    flags = win32net.NetUserGetInfo(None, cuenta_externa, 1)["flags"]
    win32net.NetUserSetInfo(None, cuenta_externa, 1008,
                            {"flags": flags | win32netcon.UF_ACCOUNTDISABLE})

    nombres = {c["usuario"].lower() for c in accounts.cuentas_incorporables()}
    assert cuenta_externa not in nombres


@requiere_admin
def test_incorporar_no_cambia_la_cuenta_de_windows(raiz, cuenta_externa):
    from custodia.core import accounts, config

    info = accounts.incorporar_usuario(cuenta_externa)

    assert config.APP_GROUP in info.grupos and not info.es_admin
    assert not info.creada_por_custodia
    assert _puede_entrar(cuenta_externa, CONTRASENA)
    assert (raiz / cuenta_externa).is_dir()
    assert cuenta_externa in {c.username.lower() for c in accounts.listar_usuarios()}


@requiere_admin
def test_incorporar_como_administrador(raiz, cuenta_externa):
    from custodia.core import accounts

    assert accounts.incorporar_usuario(cuenta_externa, es_admin=True).es_admin
    assert accounts.es_admin(cuenta_externa)


@requiere_admin
@pytest.mark.parametrize("nombre", ["Administrator", "Administrador", "Guest"])
def test_las_integradas_no_se_incorporan(grupos_app, nombre):
    from custodia.core import accounts
    from custodia.core.errors import ProtectedAccount

    with pytest.raises(ProtectedAccount):
        accounts.incorporar_usuario(nombre)


@requiere_admin
def test_no_se_incorpora_una_cuenta_inexistente(grupos_app):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    with pytest.raises(AccountError, match="no existe"):
        accounts.incorporar_usuario("no_existe_jamas_xyz")


@requiere_admin
def test_una_incorporada_no_se_borra(raiz, cuenta_externa):
    from custodia.core import accounts
    from custodia.core.errors import ProtectedAccount

    accounts.incorporar_usuario(cuenta_externa, es_admin=True)

    with pytest.raises(ProtectedAccount, match="ya existía"):
        accounts.eliminar_usuario(cuenta_externa)
    assert _existe(cuenta_externa)


@requiere_admin
def test_retirar_conserva_la_cuenta_de_windows(raiz, cuenta_externa):
    from custodia.core import accounts, config

    accounts.incorporar_usuario(cuenta_externa, es_admin=True)

    accounts.retirar_de_custodia(cuenta_externa)

    assert _puede_entrar(cuenta_externa, CONTRASENA)
    grupos = accounts._grupos_de(cuenta_externa)
    assert config.APP_GROUP not in grupos and config.ADMIN_GROUP not in grupos
    assert cuenta_externa not in {c.username.lower() for c in accounts.listar_usuarios()}


@requiere_admin
def test_retirar_a_quien_no_es_administrador(raiz, usuario_prueba):
    """No estar en el grupo de administradores no debe impedir retirarla."""
    from custodia.core import accounts

    cuenta, password = usuario_prueba
    try:
        accounts.retirar_de_custodia(cuenta.username)

        assert not accounts.es_miembro_app(cuenta.username)
        assert _puede_entrar(cuenta.username, password)
    finally:
        # Ya retirada, la salvaguarda impide que la fixture la borre.
        _borrar_cuenta(cuenta.username)


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

@requiere_admin
def test_crear_listar_y_eliminar_un_grupo(grupo):
    from custodia.core import accounts

    entrada = next(g for g in accounts.listar_grupos() if g["name"] == grupo)
    assert entrada["description"] == "Grupo de prueba"

    accounts.eliminar_grupo(grupo)
    assert grupo not in {g["name"] for g in accounts.listar_grupos()}


@requiere_admin
def test_grupo_duplicado_o_inexistente(grupo):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    with pytest.raises(AccountError, match="ya existe"):
        accounts.crear_grupo(grupo)
    with pytest.raises(AccountError, match="no existe"):
        accounts.eliminar_grupo("cust_grp_no_existe")


@requiere_admin
def test_la_pertenencia_a_un_grupo_la_ve_windows(raiz, usuario_prueba, grupo):
    from custodia.core import accounts

    cuenta, _ = usuario_prueba

    accounts.anadir_a_grupo(grupo, cuenta.username)
    accounts.añadir_a_grupo(grupo, cuenta.username)   # repetir no es un error

    assert grupo in accounts.info_usuario(cuenta.username).grupos


@requiere_admin
def test_quitar_de_un_grupo_lo_ve_windows(raiz, usuario_prueba, grupo):
    from custodia.core import accounts

    cuenta, _ = usuario_prueba
    accounts.añadir_a_grupo(grupo, cuenta.username)

    accounts.quitar_de_grupo(grupo, cuenta.username)

    assert grupo not in accounts.info_usuario(cuenta.username).grupos


@requiere_admin
def test_quitar_de_un_grupo_al_que_no_pertenece(raiz, usuario_prueba, grupo):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    cuenta, _ = usuario_prueba
    with pytest.raises(AccountError, match="No se pudo quitar"):
        accounts.quitar_de_grupo(grupo, cuenta.username)


@requiere_admin
def test_anadir_a_un_grupo_inexistente(raiz, usuario_prueba):
    from custodia.core import accounts
    from custodia.core.errors import AccountError

    cuenta, _ = usuario_prueba
    with pytest.raises(AccountError, match="No se pudo añadir"):
        accounts.añadir_a_grupo("cust_grp_no_existe", cuenta.username)
