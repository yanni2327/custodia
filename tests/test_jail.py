# -*- coding: utf-8 -*-
"""
Pruebas del confinamiento de rutas.

Son las únicas que no necesitan privilegios de administrador, así que son las
primeras que deberías hacer pasar.
"""
from __future__ import annotations

import pytest

from conftest import pytestmark  # noqa: F401  (aplica el skip si no es Windows)


def test_ruta_vacia_es_la_raiz(raiz):
    from custodia.core import jail
    assert jail.resolve("") == raiz.resolve()
    assert jail.resolve("/") == raiz.resolve()


def test_ruta_normal(raiz):
    from custodia.core import jail
    assert jail.resolve("documentos/informe.txt") == (
        raiz / "documentos" / "informe.txt"
    ).resolve()


def test_acepta_separadores_de_windows(raiz):
    from custodia.core import jail
    assert jail.resolve(r"documentos\informe.txt") == jail.resolve("documentos/informe.txt")


@pytest.mark.parametrize("intento", [
    "../secreto.txt",
    "documentos/../../fuera.txt",
    "..",
    "a/b/../../../..",
    r"..\..\Windows\System32\config\SAM",
])
def test_rechaza_fuga_hacia_arriba(raiz, intento):
    from custodia.core import jail
    from custodia.core.errors import PathOutsideJail

    with pytest.raises(PathOutsideJail):
        jail.resolve(intento)


@pytest.mark.parametrize("nombre", [
    "archivo<malo.txt",
    'archivo"malo.txt',
    "archivo|malo.txt",
    "archivo?.txt",
    "archivo*.txt",
])
def test_rechaza_caracteres_prohibidos(nombre):
    from custodia.core import jail
    from custodia.core.errors import InvalidPathName

    with pytest.raises(InvalidPathName):
        jail.validar_nombre(nombre)


@pytest.mark.parametrize("nombre", ["CON", "PRN", "NUL", "COM1", "LPT9", "con.txt", "AUX.log"])
def test_rechaza_nombres_reservados_de_windows(nombre):
    from custodia.core import jail
    from custodia.core.errors import InvalidPathName

    with pytest.raises(InvalidPathName):
        jail.validar_nombre(nombre)


def test_rechaza_flujos_alternativos_de_ntfs():
    """
    'informe.txt:oculto' crea un flujo de datos alternativo: contenido escondido
    dentro de un archivo que en el listado se ve normal y con tamaño 0.
    """
    from custodia.core import jail
    from custodia.core.errors import InvalidPathName

    with pytest.raises(InvalidPathName):
        jail.validar_nombre("informe.txt:oculto")


@pytest.mark.parametrize("nombre", ["informe.txt ", "carpeta.", "nombre..."])
def test_rechaza_punto_o_espacio_final(nombre):
    """
    Windows los recorta en silencio, así que 'informe.txt ' e 'informe.txt'
    acaban siendo el mismo archivo. Eso permite burlar comprobaciones por nombre.
    """
    from custodia.core import jail
    from custodia.core.errors import InvalidPathName

    with pytest.raises(InvalidPathName):
        jail.validar_nombre(nombre)


def test_ruta_virtual_de_ida_y_vuelta(raiz):
    from custodia.core import jail

    original = "documentos/2026/informe.txt"
    fisica = jail.resolve(original)
    assert jail.to_virtual(fisica) == "/" + original


def test_la_raiz_en_virtual_es_barra(raiz):
    from custodia.core import jail
    assert jail.to_virtual(raiz) == "/"
