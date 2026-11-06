# -*- coding: utf-8 -*-
"""
Confirmación de operaciones sensibles con el segundo factor.

Antes de eliminar, descargar, cambiar permisos o administrar cuentas, la
interfaz pide el código de la app de autenticación (`Sesion.confirmar_operacion`).
Estas pruebas fijan las tres reglas que lo hacen seguro:

1. Un código aceptado no sirve otra vez (ni el del inicio de sesión).
2. Un código incorrecto cuenta para el bloqueo de la cuenta y queda en la
   bitácora con la operación que se intentaba.
3. Con la cuenta bloqueada no se acepta nada.

No tocan Windows: se sustituyen la verificación TOTP, el contador de intentos
y la bitácora.
"""
from __future__ import annotations

import pytest

from custodia.core.errors import AuthenticationError
from custodia.gui import sesion as modulo_sesion
from custodia.gui.sesion import Sesion


@pytest.fixture
def entorno(monkeypatch):
    estado = {"codigos": {"111111": 100, "222222": 101}, "fallos": 0,
              "limite": 3, "bitacora": []}

    monkeypatch.setattr(modulo_sesion.segundofactor, "verificar_contador",
                        lambda usuario, codigo: estado["codigos"].get(codigo))

    def registrar_fallo(usuario):
        estado["fallos"] += 1
        return estado["fallos"] >= estado["limite"], 0

    monkeypatch.setattr(modulo_sesion.seguridad, "registrar_fallo", registrar_fallo)
    monkeypatch.setattr(modulo_sesion.seguridad, "esta_bloqueado",
                        lambda usuario: (estado["fallos"] >= estado["limite"], 300))
    monkeypatch.setattr(modulo_sesion.seguridad, "limpiar",
                        lambda usuario: estado.update(fallos=0))
    monkeypatch.setattr(modulo_sesion.audit, "registrar",
                        lambda *a, **k: estado["bitacora"].append((a, k)))
    return estado


def _sesion(ultimo: int = -1) -> Sesion:
    return Sesion(username="ana", token=None, es_admin=False, ultimo_contador=ultimo)


def test_codigo_correcto_autoriza_y_queda_en_la_bitacora(entorno):
    s = _sesion()
    assert s.confirmar_operacion("111111", "eliminar: /ana/x.pdf") == "ok"
    (args, kwargs), = entorno["bitacora"]
    assert args[1] == "segundo_factor_ok" and kwargs["detalle"] == "eliminar: /ana/x.pdf"


def test_un_codigo_no_sirve_dos_veces(entorno):
    s = _sesion()
    assert s.confirmar_operacion("111111", "eliminar") == "ok"
    assert s.confirmar_operacion("111111", "descargar") == "usado"
    # Reutilizar no es adivinar: no penaliza.
    assert entorno["fallos"] == 0
    # El siguiente código sí vale.
    assert s.confirmar_operacion("222222", "descargar") == "ok"


def test_el_codigo_del_inicio_de_sesion_no_vale_para_operar(entorno):
    s = _sesion(ultimo=100)            # entró con el código del paso 100
    assert s.confirmar_operacion("111111", "eliminar") == "usado"


def test_codigo_incorrecto_cuenta_para_el_bloqueo(entorno):
    s = _sesion()
    assert s.confirmar_operacion("999999", "renombrar") == "incorrecto"
    assert entorno["fallos"] == 1
    (args, kwargs), = entorno["bitacora"]
    assert args[1] == "fallo_segundo_factor" and kwargs["exito"] is False
    assert kwargs["detalle"] == "renombrar"


def test_admin_restablece_la_verificacion_de_otra_cuenta(entorno, monkeypatch):
    quitadas = []
    monkeypatch.setattr(modulo_sesion.segundofactor, "desactivar", quitadas.append)
    admin = Sesion(username="ana", token=None, es_admin=True)
    admin.restablecer_segundo_factor("juan")
    assert quitadas == ["juan"]
    (args, kwargs), = entorno["bitacora"]
    assert args[1] == "segundo_factor_restablecido" and kwargs["detalle"] == "juan"


def test_restablecer_no_vale_para_la_propia_cuenta_ni_sin_ser_admin(entorno, monkeypatch):
    quitadas = []
    monkeypatch.setattr(modulo_sesion.segundofactor, "desactivar", quitadas.append)
    with pytest.raises(PermissionError):
        Sesion(username="ana", token=None, es_admin=True).restablecer_segundo_factor("ANA")
    with pytest.raises(PermissionError):
        Sesion(username="juan", token=None, es_admin=False).restablecer_segundo_factor("ana")
    assert quitadas == []


def test_demasiados_fallos_bloquean_y_ya_no_se_acepta_nada(entorno):
    s = _sesion()
    s.confirmar_operacion("999999", "eliminar")
    s.confirmar_operacion("999999", "eliminar")
    with pytest.raises(AuthenticationError):
        s.confirmar_operacion("999999", "eliminar")        # tercer fallo: bloquea
    with pytest.raises(AuthenticationError):
        s.confirmar_operacion("222222", "eliminar")        # ni con el correcto
