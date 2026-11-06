# -*- coding: utf-8 -*-
"""
Pruebas del cifrado en reposo (RF-08, RNF-08).

La prueba que respalda el RF-08 es `test_en_disco_no_es_legible`: abre el
archivo directamente, saltándose la aplicación, y comprueba que el contenido
no aparece. Es exactamente el criterio de verificación que pide la propuesta.
"""
from __future__ import annotations

import os
import time

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


@requiere_admin
def test_ida_y_vuelta(clave_maestra):
    from custodia.core import crypto

    original = b"contenido confidencial del expediente 2026-0142"
    assert crypto.descifrar(crypto.cifrar(original)) == original


@requiere_admin
def test_soporta_binarios_y_vacios(clave_maestra):
    """El modelo anterior guardaba el contenido en una columna de texto y no
    admitía binarios. Este acepta cualquier secuencia de bytes."""
    from custodia.core import crypto

    for datos in (b"", b"\x00\xff\xfe\x01", os.urandom(4096)):
        assert crypto.descifrar(crypto.cifrar(datos)) == datos


@requiere_admin
def test_el_nonce_nunca_se_repite(clave_maestra):
    """
    Cifrar dos veces el mismo contenido debe dar resultados distintos.

    En GCM, repetir un nonce con la misma clave rompe el esquema por completo.
    Esta prueba detecta el error clásico de derivar el nonce del contenido o
    dejarlo fijo.
    """
    from custodia.core import crypto

    datos = b"mismo contenido"
    resultados = {crypto.cifrar(datos) for _ in range(50)}
    assert len(resultados) == 50


@requiere_admin
def test_detecta_manipulacion(clave_maestra):
    """
    GCM autentica además de cifrar: alterar un byte debe hacer fallar el
    descifrado, no devolver basura silenciosamente.
    """
    from custodia.core import crypto
    from custodia.core.errors import CryptoError

    blob = bytearray(crypto.cifrar(b"saldo: 1000"))
    blob[-1] ^= 0x01   # un solo bit del cuerpo

    with pytest.raises(CryptoError, match="etiqueta de autenticación"):
        crypto.descifrar(bytes(blob))


@requiere_admin
def test_contenido_sin_cabecera_pasa_tal_cual(clave_maestra):
    """Un archivo colocado a mano en la carpeta se lee sin romper la aplicación."""
    from custodia.core import crypto

    assert crypto.descifrar(b"texto plano de antes") == b"texto plano de antes"


@requiere_admin
def test_la_clave_no_esta_en_texto_plano(clave_maestra):
    """
    Criterio de aceptación del RNF-08: la clave no debe aparecer en claro en
    disco. Lo que hay en el archivo es un blob de DPAPI.
    """
    from pathlib import Path

    from custodia.core import config, crypto

    blob = Path(config.KEY_FILE).read_bytes()
    clave = crypto._clave_maestra()

    assert clave not in blob
    assert len(clave) == 32
    assert len(blob) > 32   # DPAPI añade su propia estructura


@requiere_admin
def test_en_disco_no_es_legible(usuario_prueba, raiz, clave_maestra):
    """
    RF-08. Se escribe un archivo por la aplicación y se lee después
    directamente del disco, sin pasar por ella. El contenido no debe aparecer.
    """
    from custodia.core import auth, fsops
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba
    secreto = b"NUMERO_DE_CUENTA_4471829930"

    destino = raiz / "expediente.txt"
    from custodia.core import acl
    from custodia.core.acl import Perm
    acl.conceder(raiz, cuenta.username, Perm.TOTAL)

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            fsops.escribir(destino, secreto)
    finally:
        token.Close()

    en_disco = destino.read_bytes()
    assert secreto not in en_disco
    assert en_disco.startswith(b"CUSTODIA")

    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            assert fsops.leer(destino) == secreto
    finally:
        token.Close()


@requiere_admin
def test_tamano_original_sin_descifrar(clave_maestra, raiz):
    """La cabecera permite mostrar el peso real en un listado leyendo 29 bytes."""
    from custodia.core import crypto

    datos = os.urandom(10_000)
    archivo = raiz / "pesado.bin"
    archivo.write_bytes(crypto.cifrar(datos))

    assert crypto.tamano_original(archivo) == 10_000
    assert archivo.stat().st_size > 10_000   # cabecera + etiqueta GCM


@requiere_admin
def test_rendimiento_rnf08(clave_maestra):
    """
    RNF-08: el cifrado no debe añadir más de 200 ms sobre un archivo de 10 MB,
    promediado sobre 20 ejecuciones.
    """
    from custodia.core import crypto

    datos = os.urandom(10 * 1024 * 1024)

    inicio = time.perf_counter()
    for _ in range(20):
        crypto.descifrar(crypto.cifrar(datos))
    promedio_ms = (time.perf_counter() - inicio) / 20 * 1000

    print(f"\n  Cifrado+descifrado de 10 MB: {promedio_ms:.1f} ms de promedio")
    assert promedio_ms < 200, (
        f"{promedio_ms:.1f} ms supera el límite de 200 ms del RNF-08"
    )


@requiere_admin
def test_la_clave_no_se_lee_dentro_de_la_suplantacion(usuario_prueba, clave_maestra):
    """
    Regresión sobre una decisión de arquitectura.

    El archivo de clave solo lo pueden leer Administradores y SYSTEM. Si la
    carga ocurriera dentro de un bloque de suplantación, Windows la denegaría.
    La aplicación la precarga al arrancar; esta prueba verifica que, si alguien
    rompe ese orden, el error explica la causa en lugar de aparecer como un
    "Acceso denegado" a una ruta sin relación aparente con la operación.
    """
    from custodia.core import auth, crypto
    from custodia.core.errors import CryptoError
    from custodia.core.impersonate import impersonate

    cuenta, password = usuario_prueba

    crypto.olvidar_clave()   # simular que nadie precargó
    token = auth.logon(cuenta.username, password)
    try:
        with impersonate(token):
            with pytest.raises(CryptoError, match="precargar_clave"):
                crypto.cifrar(b"datos")
    finally:
        token.Close()
        crypto.precargar_clave()   # restaurar para el resto de la sesión
