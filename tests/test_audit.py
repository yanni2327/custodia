# -*- coding: utf-8 -*-
"""
Pruebas de la bitácora (RF-05).

El criterio de verificación de la propuesta es inspeccionar la tabla de
bitácora en SQLite tras ejecutar una secuencia de operaciones de prueba. Eso es
literalmente lo que hace `test_rf05_secuencia_de_operaciones`.
"""
from __future__ import annotations

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


@requiere_admin
def test_rf05_secuencia_de_operaciones(usuario_prueba, raiz, bitacora,
                                       clave_maestra):
    """
    RF-05. Se ejecuta una secuencia mixta —operaciones permitidas y denegadas—
    y se comprueba que la bitácora recoge usuario, acción, recurso y resultado.
    """
    from custodia.core import acl, audit, auth, fsops
    from custodia.core.acl import Perm
    from custodia.core.errors import PermissionDenied
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba
    acl.conceder(raiz, cuenta.username, Perm.TOTAL)

    vetada = raiz / "vetada"
    vetada.mkdir()
    acl.establecer_permisos(
        vetada, [("Administrators", int(Perm.TOTAL), True, True)],
        romper_herencia=True,
    )

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            fsops.crear_carpeta(raiz / "informes")
            fsops.escribir(raiz / "informes" / "acta.txt", b"contenido")
            fsops.leer(raiz / "informes" / "acta.txt")

            with pytest.raises(PermissionDenied):
                fsops.listar(vetada)
    finally:
        token.Close()

    eventos = audit.consultar(usuario=cuenta.username, limite=50)
    acciones = {(e["accion"], e["exito"]) for e in eventos}

    assert ("crear_carpeta", True) in acciones
    assert ("escribir", True) in acciones
    assert ("leer", True) in acciones
    assert ("listar", False) in acciones, "El intento denegado no quedó registrado"


@requiere_admin
def test_el_usuario_registrado_es_el_suplantado(usuario_prueba, raiz, bitacora,
                                                clave_maestra):
    """
    El usuario se toma de la identidad efectiva del hilo, no de un parámetro.
    Así la bitácora registra a quien el kernel vio ejecutar la operación.
    """
    from custodia.core import acl, audit, auth, fsops
    from custodia.core.acl import Perm
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba
    acl.conceder(raiz, cuenta.username, Perm.TOTAL)

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            fsops.crear_carpeta(raiz / "suya")
    finally:
        token.Close()

    eventos = audit.consultar(accion="crear_carpeta", limite=10)
    assert eventos
    assert eventos[0]["usuario"].lower() == cuenta.username.lower()


@requiere_admin
def test_filtro_de_denegados(usuario_prueba, raiz, bitacora, clave_maestra):
    """
    El filtro que responde la pregunta útil: quién intentó acceder a algo que
    no le correspondía.
    """
    from custodia.core import acl, audit, auth, fsops
    from custodia.core.acl import Perm
    from custodia.core.errors import PermissionDenied
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba

    vetada = raiz / "confidencial"
    vetada.mkdir()
    acl.establecer_permisos(
        vetada, [("Administrators", int(Perm.TOTAL), True, True)],
        romper_herencia=True,
    )

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            for _ in range(3):
                with pytest.raises(PermissionDenied):
                    fsops.listar(vetada)
    finally:
        token.Close()

    denegados = audit.consultar(solo_denegados=True, limite=50)
    assert len(denegados) >= 3
    assert all(e["exito"] is False for e in denegados)
    assert all("PermissionDenied" in (e["detalle"] or "") for e in denegados)


@requiere_admin
def test_registrar_funciona_bajo_suplantacion(usuario_prueba, bitacora):
    """
    Regresión sobre la decisión de arquitectura.

    Si la bitácora se escribiera de forma síncrona, esta llamada fallaría: el
    usuario suplantado no tiene permiso sobre el archivo de la base de datos.
    Como `registrar` solo encola en memoria, funciona desde cualquier identidad
    y el hilo escritor la vuelca después con los privilegios de la aplicación.
    """
    from custodia.core import audit, auth
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            audit.registrar(cuenta.username, "prueba_sintetica", "/x", exito=True)
    finally:
        token.Close()

    eventos = audit.consultar(accion="prueba_sintetica", limite=5)
    assert eventos
    assert eventos[0]["usuario"].lower() == cuenta.username.lower()


@requiere_admin
def test_registrar_nunca_lanza_sin_inicializar():
    """
    Anotar sin haber inicializado la bitácora no debe romper nada: perder un
    registro es preferible a tumbar la operación del usuario.
    """
    from custodia.core import audit

    audit.close()
    audit.registrar("alguien", "accion", "/ruta")   # no debe lanzar
    assert audit.consultar() == []
