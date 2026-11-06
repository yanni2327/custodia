# -*- coding: utf-8 -*-
"""
Pruebas del contrato de permisos (RNF-03, RF-07).

El criterio de aceptación del RNF-03 dice que la suite del núcleo debe pasar
sin cambios contra ambas implementaciones. Por eso las pruebas del contrato
están parametrizadas: cada una se ejecuta dos veces, una contra el backend de
Windows y otra contra el doble de prueba, con el mismo cuerpo. Si una
implementación se desvía del contrato, la prueba falla solo para ella.

Al final hay pruebas específicas del backend real, las que verifican que la
respuesta viene de Windows y no de nuestro código.
"""
from __future__ import annotations

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


# ---------------------------------------------------------------------------
# Pruebas del contrato: se ejecutan contra los dos backends
# ---------------------------------------------------------------------------

@requiere_admin
def test_sin_permisos_no_puede(backend, sujeto, archivo_de_prueba):
    from custodia.core.permissions import Accion

    assert backend.can(sujeto, archivo_de_prueba, Accion.LEER) is False


@requiere_admin
def test_conceder_habilita_la_accion(backend, sujeto, archivo_de_prueba):
    from custodia.core.permissions import Accion

    backend.conceder(sujeto, archivo_de_prueba, {Accion.LEER}, hereda=False)
    assert backend.can(sujeto, archivo_de_prueba, Accion.LEER) is True


@requiere_admin
def test_conceder_una_accion_no_habilita_otra(backend, sujeto, archivo_de_prueba):
    """Conceder lectura no debe habilitar el cambio de permisos."""
    from custodia.core.permissions import Accion

    backend.conceder(sujeto, archivo_de_prueba, {Accion.LEER}, hereda=False)
    assert backend.can(sujeto, archivo_de_prueba, Accion.CAMBIAR_PERMISOS) is False


@requiere_admin
def test_permisos_efectivos_refleja_lo_concedido(backend, sujeto, archivo_de_prueba):
    """RF-07: es lo que la interfaz pintará en el panel de permisos."""
    from custodia.core.permissions import Accion

    backend.conceder(sujeto, archivo_de_prueba, {Accion.LEER, Accion.ESCRIBIR},
                     hereda=False)
    efectivos = backend.permisos_efectivos(sujeto, archivo_de_prueba)

    assert Accion.LEER in efectivos
    assert Accion.ESCRIBIR in efectivos


@requiere_admin
def test_permisos_efectivos_vacio_sin_concesiones(backend, sujeto, archivo_de_prueba):
    assert backend.permisos_efectivos(sujeto, archivo_de_prueba) == set()


# ---------------------------------------------------------------------------
# Específicas del backend real
# ---------------------------------------------------------------------------

@requiere_admin
def test_la_respuesta_coincide_con_la_operacion_real(usuario_prueba, raiz,
                                                     clave_maestra):
    """
    La prueba que amarra los dos caminos.

    `can()` sondea por adelantado abriendo un manejador; `fsops.leer()` intenta la
    operación bajo suplantación. Como ambos terminan en el mismo motor de
    autorización del sistema, no pueden contradecirse. Si esta prueba fallara,
    significaría que uno de los dos caminos dejó de consultar a Windows.
    """
    from custodia.core import acl, auth, fsops, permissions
    from custodia.core.acl import Perm
    from custodia.core.backends.windows import BackendWindows
    from custodia.core.errors import PermissionDenied
    from custodia.core.impersonate import impersonate
    from custodia.core.permissions import Accion, Sujeto

    cuenta, password = usuario_prueba
    backend = BackendWindows()

    publico = raiz / "publico.txt"
    privado = raiz / "privado.txt"
    for ruta in (publico, privado):
        ruta.write_bytes(b"contenido")
        acl.establecer_permisos(
            ruta, [("Administrators", int(Perm.TOTAL), True, False)],
            romper_herencia=True,
        )
    acl.conceder(publico, cuenta.username, Perm.LEER, hereda_a_hijos=False)

    token = auth.logon(cuenta.username, password)
    try:
        sujeto = Sujeto(cuenta.username, token)

        # Lo que anticipa el sondeo
        assert backend.can(sujeto, publico, Accion.LEER) is True
        assert backend.can(sujeto, privado, Accion.LEER) is False

        # Lo que ocurre al intentarlo de verdad
        with impersonate(token):
            assert fsops.leer(publico) == b"contenido"
            with pytest.raises(PermissionDenied):
                fsops.leer(privado)
    finally:
        token.Close()


@requiere_admin
def test_la_denegacion_explicita_gana(usuario_prueba, raiz):
    """El kernel aplica el orden canónico de NTFS: denegar vence a permitir."""
    from custodia.core import acl, auth
    from custodia.core.acl import Perm
    from custodia.core.backends.windows import BackendWindows
    from custodia.core.permissions import Accion, Sujeto

    cuenta, password = usuario_prueba
    archivo = raiz / "contradictorio.txt"
    archivo.write_bytes(b"datos")

    acl.conceder(archivo, cuenta.username, Perm.LEER, hereda_a_hijos=False)
    acl.denegar(archivo, cuenta.username, Perm.LEER, hereda_a_hijos=False)

    token = auth.logon(cuenta.username, password)
    try:
        sujeto = Sujeto(cuenta.username, token)
        assert BackendWindows().can(sujeto, archivo, Accion.LEER) is False
    finally:
        token.Close()


@requiere_admin
def test_hereda_los_permisos_de_grupo(usuario_prueba, raiz):
    """
    El token trae los SID de los grupos del usuario, así que un permiso
    concedido al grupo funciona sin nombrar a la persona. Reproducir esto a
    mano exigiría resolver la pertenencia a grupos: aquí lo hizo Windows al
    emitir el token.
    """
    from custodia.core import acl, auth, config
    from custodia.core.acl import Perm
    from custodia.core.backends.windows import BackendWindows
    from custodia.core.permissions import Accion, Sujeto

    cuenta, password = usuario_prueba
    archivo = raiz / "del_grupo.txt"
    archivo.write_bytes(b"datos")

    acl.establecer_permisos(
        archivo,
        [
            ("Administrators", int(Perm.TOTAL), True, False),
            (config.APP_GROUP, int(Perm.LEER), True, False),   # al grupo, no al usuario
        ],
        romper_herencia=True,
    )

    token = auth.logon(cuenta.username, password)
    try:
        sujeto = Sujeto(cuenta.username, token)
        assert BackendWindows().can(sujeto, archivo, Accion.LEER) is True
    finally:
        token.Close()


@requiere_admin
def test_can_se_niega_dentro_de_una_suplantacion(usuario_prueba, raiz):
    """
    Guardia de diseño. `can()` suplanta internamente lo justo para hacer el
    sondeo, así que llamarlo desde dentro de otra suplantación anidaría dos, y
    revertir la interna dejaría el hilo con los privilegios de la aplicación.
    """
    from custodia.core import auth
    from custodia.core.backends.windows import BackendWindows
    from custodia.core.impersonate import impersonate
    from custodia.core.permissions import Accion, Sujeto

    cuenta, password = usuario_prueba
    archivo = raiz / "cualquiera.txt"
    archivo.write_bytes(b"datos")

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            with pytest.raises(RuntimeError, match="dentro de una suplantación"):
                BackendWindows().can(Sujeto(cuenta.username, token), archivo,
                                     Accion.LEER)
    finally:
        token.Close()


@requiere_admin
def test_sujeto_sin_token_da_error_claro(raiz):
    from custodia.core.backends.windows import BackendWindows
    from custodia.core.permissions import Accion, Sujeto

    archivo = raiz / "x.txt"
    archivo.write_bytes(b"datos")

    with pytest.raises(ValueError, match="no trae token"):
        BackendWindows().can(Sujeto("alguien"), archivo, Accion.LEER)
