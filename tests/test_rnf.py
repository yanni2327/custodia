# -*- coding: utf-8 -*-
"""
Pruebas de los requisitos no funcionales con criterio de aceptación numérico.

La propuesta define para varios RNF un criterio verificable concreto (100
operaciones, 50 intentos, promedio de 20 ejecuciones). Cada uno tiene aquí su
prueba, con el número exacto que exige el documento, para poder citarlas en la
sustentación.
"""
from __future__ import annotations

import os
import time

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


@requiere_admin
def test_rnf01_sin_suplantaciones_remanentes(usuario_prueba):
    """
    RNF-01. Criterio: cero suplantaciones activas remanentes tras 100
    operaciones consecutivas.

    Se alternan operaciones que terminan bien y operaciones que lanzan
    excepción, porque el riesgo real no está en el camino feliz sino en el
    fallo a mitad de la operación.
    """
    from custodia.core import auth
    from custodia.core.impersonate import current_identity, impersonate, is_impersonating

    cuenta, password = usuario_prueba
    yo = current_identity()

    token = auth.logon(cuenta.username, password)
    try:
        for i in range(100):
            if i % 3 == 0:
                with pytest.raises(RuntimeError):
                    with impersonate(token):
                        assert is_impersonating()
                        raise RuntimeError("fallo simulado")
            else:
                with impersonate(token):
                    assert current_identity().lower() == cuenta.username.lower()

            assert not is_impersonating(), f"Suplantación remanente en la vuelta {i}"
            assert current_identity() == yo, f"Identidad contaminada en la vuelta {i}"
    finally:
        token.Close()


@requiere_admin
def test_rnf05_ninguna_denegacion_deja_archivos_parciales(usuario_prueba, raiz,
                                                          clave_maestra):
    """
    RNF-05. Criterio: cero archivos corruptos o parciales tras 50 intentos de
    operación denegada.

    Se le niega al usuario el permiso de escritura sobre la carpeta y se
    intentan 50 escrituras de 1 MB. Ninguna debe dejar rastro: ni el archivo
    destino, ni un temporal huérfano.
    """
    from custodia.core import acl, auth, fsops
    from custodia.core.acl import Perm
    from custodia.core.errors import PermissionDenied
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba

    protegida = raiz / "solo_lectura"
    protegida.mkdir()
    acl.establecer_permisos(
        protegida,
        [
            ("Administrators", int(Perm.TOTAL), True, True),
            (cuenta.username, int(Perm.LEER), True, True),
        ],
        romper_herencia=True,
    )

    antes = set(os.listdir(protegida))
    datos = os.urandom(1024 * 1024)

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            for i in range(50):
                with pytest.raises(PermissionDenied):
                    fsops.escribir(protegida / f"intento_{i}.bin", datos)
    finally:
        token.Close()

    despues = set(os.listdir(protegida))
    assert despues == antes, f"Quedaron archivos tras las denegaciones: {despues - antes}"

    huerfanos = [n for n in despues if n.endswith(".tmp")]
    assert not huerfanos, f"Temporales huérfanos: {huerfanos}"


@requiere_admin
def test_rnf02_rendimiento_de_lectura_y_escritura(usuario_prueba, raiz, clave_maestra):
    """
    RNF-02. Criterio: una operación sobre un archivo de hasta 10 MB, incluida
    la suplantación, no supera 500 ms. Promedio sobre 20 ejecuciones.
    """
    from custodia.core import acl, auth, fsops
    from custodia.core.acl import Perm
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba
    acl.conceder(raiz, cuenta.username, Perm.TOTAL)

    datos = os.urandom(10 * 1024 * 1024)
    destino = raiz / "medicion.bin"

    tiempos = []
    for _ in range(20):
        inicio = time.perf_counter()
        token = auth.logon(cuenta.username, password)
        try:
            with impersonate(token):
                fsops.escribir(destino, datos, sobrescribir=True)
                fsops.leer(destino)
        finally:
            token.Close()
        tiempos.append((time.perf_counter() - inicio) * 1000)

    promedio = sum(tiempos) / len(tiempos)
    print(f"\n  Escritura+lectura de 10 MB con suplantación: {promedio:.1f} ms")
    assert promedio < 500, f"{promedio:.1f} ms supera el límite de 500 ms del RNF-02"


@requiere_admin
def test_sobrescribir_conserva_los_permisos(usuario_prueba, raiz, clave_maestra):
    """
    Regresión. `os.replace` sustituye el archivo entero, incluida su DACL, así
    que guardar un archivo borraría los permisos que alguien le hubiera puesto.
    `escribir` los rescata y los reaplica.
    """
    from custodia.core import acl, fsops
    from custodia.core.acl import Perm
    from custodia.core.impersonate import impersonate
    from custodia.core import auth

    cuenta, password = usuario_prueba
    acl.conceder(raiz, cuenta.username, Perm.TOTAL)

    archivo = raiz / "con_permisos.txt"
    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            fsops.escribir(archivo, b"version 1")
    finally:
        token.Close()

    acl.conceder(archivo, cuenta.username, Perm.LEER, hereda_a_hijos=False)
    sids_antes = {e.sid for e in acl.leer_permisos(archivo) if not e.heredado}

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            fsops.escribir(archivo, b"version 2", sobrescribir=True)
    finally:
        token.Close()

    sids_despues = {e.sid for e in acl.leer_permisos(archivo) if not e.heredado}
    assert sids_antes <= sids_despues, "Sobrescribir perdió entradas de la DACL"
