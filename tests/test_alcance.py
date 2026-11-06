# -*- coding: utf-8 -*-
"""
Pruebas del alcance de un usuario normal: SU carpeta y la COMPARTIDA, nada más.

Se aísla del sistema: el almacén es una carpeta temporal y no se suplanta a
nadie (`info` se sustituye), así que la lógica de la fachada se prueba sin
privilegios. Lo que impone el kernel —la ACL de la raíz— se comprueba aparte
con la constante que se escribe en ella.
"""
from __future__ import annotations

import pytest

from custodia.core import acl, config, espacios
from custodia.core.errors import PermissionDenied
from custodia.core.fsops import NodoInfo
from custodia.gui import sesion as modulo_sesion
from custodia.gui.sesion import Sesion


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STORAGE_ROOT", tmp_path)
    for nombre in ("ana", "luis", espacios.COMPARTIDA, "suelta"):
        (tmp_path / nombre).mkdir()
    monkeypatch.setattr(modulo_sesion.audit, "registrar", lambda *a, **k: None)
    yield tmp_path


def _sesion(usuario: str, es_admin: bool, monkeypatch) -> Sesion:
    s = Sesion(username=usuario, token=None, es_admin=es_admin)

    def info_falsa(ruta_virtual):
        nombre = ruta_virtual.strip("/")
        return NodoInfo(nombre=nombre, ruta=ruta_virtual, es_carpeta=True,
                        tamano=0, creado="", modificado="", propietario=None,
                        tamano_claro=None, cifrado=False)

    monkeypatch.setattr(s, "info", info_falsa)
    return s


def test_usuario_solo_ve_su_carpeta_y_la_compartida(almacen, monkeypatch):
    s = _sesion("ana", False, monkeypatch)
    nombres = {n.nombre for n in s.listar("/")}
    assert nombres == {"ana", espacios.COMPARTIDA}   # ni «luis» ni «suelta»


def test_la_raiz_no_se_enumera_para_un_usuario(almacen, monkeypatch):
    s = _sesion("ana", False, monkeypatch)
    # Si la fachada intentara listar la raíz real, usaría fsops.listar.
    monkeypatch.setattr(modulo_sesion.fsops, "listar",
                        lambda *a, **k: pytest.fail("no debe enumerar la raíz"))
    s.listar("/")
    s.listar("")


def test_espacios_base_fijos(almacen, monkeypatch):
    s = _sesion("ana", False, monkeypatch)
    assert s.es_espacio_base("/ana")
    assert s.es_espacio_base("/Compartida/")
    assert not s.es_espacio_base("/ana/informes")
    with pytest.raises(PermissionDenied):
        s.eliminar("/ana", recursivo=True)
    with pytest.raises(PermissionDenied):
        s.renombrar("/Compartida", "otra")


def test_usuario_no_crea_en_la_raiz(almacen, monkeypatch):
    s = _sesion("ana", False, monkeypatch)
    with pytest.raises(PermissionDenied):
        s.crear_carpeta("/", "mia")
    with pytest.raises(PermissionDenied):
        s.escribir("/archivo.txt", b"x")


def test_admin_conserva_todo(almacen, monkeypatch):
    s = _sesion("jefe", True, monkeypatch)
    assert s.raices_visibles() is None
    assert not s.es_espacio_base("/ana")


def test_acl_de_la_raiz_solo_permite_atravesar():
    # Lo que de verdad impone la regla es el kernel. En la raíz, el grupo de
    # usuarios solo puede atravesar: ni listar (vería carpetas ajenas) ni
    # crear subcarpetas.
    permiso = espacios._PERMISO_EN_RAIZ
    assert permiso == int(acl.Perm.EJECUTAR)
    assert not permiso & int(acl.Perm.LISTAR)
    assert not permiso & espacios._CREAR_SUBCARPETAS
