# -*- coding: utf-8 -*-
"""
Pruebas del mecanismo central: suplantación y denegación por el kernel.

Estas son las pruebas que demuestran la tesis del proyecto. Si pasan, el
control de acceso lo está aplicando Windows y no código nuestro.

Requieren consola como administrador porque crean cuentas reales.
"""
from __future__ import annotations

import threading

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


@requiere_admin
def test_la_suplantacion_cambia_la_identidad(usuario_prueba):
    from custodia.core import auth
    from custodia.core.impersonate import current_identity, impersonate

    cuenta, password = usuario_prueba
    antes = current_identity()

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            assert current_identity().lower() == cuenta.username.lower()
        assert current_identity() == antes, "RevertToSelf no restauró la identidad"
    finally:
        token.Close()


@requiere_admin
def test_la_identidad_se_restaura_aunque_haya_excepcion(usuario_prueba):
    """
    El caso que importa de verdad: si una excepción dejara el hilo suplantado,
    la siguiente petición del servidor correría con la identidad equivocada.
    """
    from custodia.core import auth
    from custodia.core.impersonate import current_identity, impersonate

    cuenta, password = usuario_prueba
    antes = current_identity()

    token = auth.logon(cuenta.username, password)
    try:
        with pytest.raises(ValueError):
            with impersonate(token):
                raise ValueError("fallo simulado a mitad de la operación")
        assert current_identity() == antes
    finally:
        token.Close()


@requiere_admin
def test_credenciales_incorrectas(usuario_prueba):
    from custodia.core import auth
    from custodia.core.errors import AuthenticationError

    cuenta, _ = usuario_prueba
    with pytest.raises(AuthenticationError):
        auth.logon(cuenta.username, "ContraseñaEquivocada!123")


@requiere_admin
def test_usuario_inexistente_da_el_mismo_error():
    """No debe poderse distinguir 'no existe' de 'contraseña mala': eso
    permitiría enumerar cuentas de la máquina."""
    from custodia.core import auth
    from custodia.core.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        auth.logon("no_existe_jamas_xyz", "loquesea123!")


@requiere_admin
def test_el_kernel_deniega_el_acceso(usuario_prueba, raiz):
    """
    LA PRUEBA CENTRAL DEL PROYECTO.

    Se crea un archivo con una DACL que no incluye al usuario de prueba, se
    suplanta a ese usuario y se intenta leerlo. La denegación tiene que venir
    de Windows.
    """
    import win32api
    from custodia.core import acl, auth
    from custodia.core.acl import Perm
    from custodia.core.errors import PermissionDenied
    from custodia.core.impersonate import impersonate, translate_denials

    cuenta, password = usuario_prueba

    privado = raiz / "privado.txt"
    privado.write_bytes(b"contenido confidencial")

    # DACL protegida: solo administradores y el propietario actual.
    yo = win32api.GetUserName()
    acl.establecer_permisos(
        privado,
        [
            ("Administrators", int(Perm.TOTAL), True, False),
            (yo, int(Perm.TOTAL), True, False),
        ],
        romper_herencia=True,
    )

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            with pytest.raises(PermissionDenied):
                with translate_denials("privado.txt"):
                    privado.read_bytes()
    finally:
        token.Close()


@requiere_admin
def test_el_kernel_permite_cuando_hay_permiso(usuario_prueba, raiz):
    """La contraparte: con un ACE de lectura, la misma operación funciona.
    Sin esta prueba, la anterior podría estar pasando por un motivo equivocado."""
    from custodia.core import acl, auth
    from custodia.core.acl import Perm
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba

    compartido = raiz / "compartido.txt"
    compartido.write_bytes(b"contenido publico")

    acl.conceder(compartido, cuenta.username, Perm.LEER, hereda_a_hijos=False)

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            assert compartido.read_bytes() == b"contenido publico"
    finally:
        token.Close()


@requiere_admin
def test_la_denegacion_gana_sobre_el_permiso(usuario_prueba, raiz):
    """
    Comportamiento canónico de NTFS: un ACE de denegación va antes en la lista y
    Windows se detiene en la primera coincidencia. Es el mismo criterio que
    implementaba a mano el proyecto anterior, ahora aplicado por el sistema.
    """
    from custodia.core import acl, auth
    from custodia.core.acl import Perm
    from custodia.core.errors import PermissionDenied
    from custodia.core.impersonate import impersonate, translate_denials

    cuenta, password = usuario_prueba

    archivo = raiz / "contradictorio.txt"
    archivo.write_bytes(b"datos")

    acl.conceder(archivo, cuenta.username, Perm.LEER, hereda_a_hijos=False)
    acl.denegar(archivo, cuenta.username, Perm.LEER, hereda_a_hijos=False)

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            with pytest.raises(PermissionDenied):
                with translate_denials():
                    archivo.read_bytes()
    finally:
        token.Close()


@requiere_admin
def test_fsops_se_niega_a_correr_sin_suplantacion(raiz):
    """
    Guardia de seguridad: sin suplantación, la operación correría con los
    privilegios administrativos del servicio y saltaría todo el control.
    """
    from custodia.core import fsops

    with pytest.raises(RuntimeError, match="sin suplantación"):
        fsops.listar(raiz)


@requiere_admin
def test_rechaza_suplantacion_anidada(usuario_prueba):
    from custodia.core import auth
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba
    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            with pytest.raises(RuntimeError, match="anidada"):
                with impersonate(token):
                    pass
    finally:
        token.Close()


@requiere_admin
def test_hilos_independientes(usuario_prueba):
    """
    La suplantación es por hilo. Un hilo suplantado no debe afectar a otro.
    Esta prueba es la que justifica que los endpoints sean `def` y no `async def`.
    """
    from custodia.core import auth
    from custodia.core.impersonate import current_identity, impersonate

    cuenta, password = usuario_prueba
    identidad_del_otro_hilo = []
    listo = threading.Event()
    seguir = threading.Event()

    def otro_hilo():
        listo.set()
        seguir.wait(timeout=5)
        identidad_del_otro_hilo.append(current_identity())

    h = threading.Thread(target=otro_hilo)
    h.start()
    listo.wait(timeout=5)

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            seguir.set()
            h.join(timeout=5)
    finally:
        token.Close()

    assert identidad_del_otro_hilo
    assert identidad_del_otro_hilo[0].lower() != cuenta.username.lower()
