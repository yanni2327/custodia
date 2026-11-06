# -*- coding: utf-8 -*-
"""
Pruebas del cifrado por usuario (bóveda de sobre con clave pública).

El núcleo criptográfico no toca Windows, así que se puede verificar entero: que
un destinatario abre el archivo, que otro no, que compartir con la clave pública
funciona sin la contraseña del otro, y que la clave privada está protegida por
contraseña.
"""
from __future__ import annotations

import pytest

from custodia.core import boveda, config, crypto


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BOVEDA_FILE", tmp_path / "identidades.json")
    monkeypatch.setattr(boveda.crypto, "proteger_solo_admin", lambda ruta: None)
    yield


def test_el_destinatario_abre_el_sobre():
    ana = boveda.generar_par()
    blob = boveda.cifrar(b"secreto", {"Ana": ana.public_key()})
    assert boveda.es_v2(blob)
    assert boveda.descifrar(blob, "ana", ana) == b"secreto"


def test_quien_no_es_destinatario_no_puede():
    ana = boveda.generar_par()
    bob = boveda.generar_par()
    blob = boveda.cifrar(b"x", {"ana": ana.public_key()})
    with pytest.raises(Exception):
        boveda.descifrar(blob, "bob", bob)


def test_compartir_no_necesita_la_contraseña_del_otro():
    ana = boveda.generar_par()
    bob = boveda.generar_par()
    blob = boveda.cifrar(b"nomina", {"ana": ana.public_key()})
    # Ana comparte con Bob usando solo la clave PÚBLICA de Bob.
    blob2 = boveda.conceder(blob, "ana", ana, "bob", bob.public_key())
    assert boveda.descifrar(blob2, "bob", bob) == b"nomina"
    assert boveda.descifrar(blob2, "ana", ana) == b"nomina"   # Ana sigue leyendo
    assert set(boveda.destinatarios(blob2)) == {"ana", "bob"}


def test_la_privada_esta_protegida_por_contraseña():
    priv = boveda.generar_par()
    blob, sal = boveda.envolver_privada(priv, "clave-de-ana")
    boveda.desenvolver_privada(blob, "clave-de-ana", sal)      # no lanza
    with pytest.raises(Exception):
        boveda.desenvolver_privada(blob, "contraseña-mala", sal)


def test_el_prefijo_es_compatible_con_v1():
    # Los primeros 29 bytes deben leerse como el formato v1, para que el listado
    # siga mostrando el tamaño y el candado sin cambios.
    ana = boveda.generar_par()
    blob = boveda.cifrar(b"1234567", {"ana": ana.public_key()})
    _, version, tam_claro = crypto._CABECERA.unpack_from(blob, 0)
    assert version == 2 and tam_claro == 7


def test_identidad_persistida(aislado):
    boveda.crear_identidad("Ana", "secreta")
    assert boveda.tiene_identidad("ana")
    priv = boveda.cargar_privada("ana", "secreta")
    assert priv is not None
    assert boveda.cargar_privada("ana", "mala") is None
    blob = boveda.cifrar(b"hola", {"ana": boveda.publica_de("ana")})
    assert boveda.descifrar(blob, "ana", priv) == b"hola"
