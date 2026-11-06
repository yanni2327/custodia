# -*- coding: utf-8 -*-
"""
Solo las cuentas de Custodia pueden entrar.

Windows valida la contraseña de cualquier cuenta del equipo; que sea correcta
no hace a nadie usuario de la aplicación. Estas pruebas fijan que una cuenta
ajena (por ejemplo, la personal del dueño del equipo antes de incorporarla)
no entra, que eso no cuenta para el bloqueo y que queda en la bitácora.

No tocan Windows: se sustituyen LogonUser, la pertenencia a grupos y lo demás.
"""
from __future__ import annotations

import pytest

from custodia.core.errors import AuthenticationError
from custodia.gui import sesion as modulo_sesion
from custodia.gui.sesion import Sesion


class _Token:
    cerrado = False

    def Close(self):
        self.cerrado = True


@pytest.fixture
def entorno(monkeypatch):
    estado = {"miembros": {"ana"}, "fallos": 0, "bitacora": [], "token": _Token()}
    m = modulo_sesion
    monkeypatch.setattr(m.seguridad, "esta_bloqueado", lambda u: (False, 0))
    monkeypatch.setattr(m.seguridad, "registrar_fallo",
                        lambda u: (estado.update(fallos=estado["fallos"] + 1), (False, 0))[1])
    monkeypatch.setattr(m.seguridad, "limpiar", lambda u: None)
    monkeypatch.setattr(m.auth, "logon", lambda u, p: estado["token"])
    monkeypatch.setattr(m.accounts, "es_miembro_app", lambda u: u in estado["miembros"])
    monkeypatch.setattr(m.accounts, "es_admin", lambda u: False)
    monkeypatch.setattr(m.segundofactor, "esta_habilitado", lambda u: False)
    monkeypatch.setattr(m.espacios, "asegurar_espacio", lambda u: None)
    monkeypatch.setattr(m.config, "CIFRADO_POR_USUARIO", False)
    monkeypatch.setattr(m.audit, "registrar",
                        lambda *a, **k: estado["bitacora"].append((a, k)))
    return estado


def test_una_cuenta_ajena_no_entra_aunque_la_contrasena_sea_correcta(entorno):
    with pytest.raises(AuthenticationError, match="no tiene acceso a Custodia"):
        Sesion.iniciar("dioya", "contraseña-correcta")
    # El token que Windows llegó a dar se cierra: no queda una sesión colgando.
    assert entorno["token"].cerrado
    # No es un intento de adivinar: no cuenta para el bloqueo.
    assert entorno["fallos"] == 0
    (args, kwargs), = entorno["bitacora"]
    assert args[1] == "inicio_sesion" and kwargs["exito"] is False
    assert "no pertenece a Custodia" in kwargs["detalle"]


def test_una_cuenta_de_custodia_entra(entorno):
    sesion = Sesion.iniciar("ana", "contraseña-correcta")
    assert sesion.username == "ana" and not entorno["token"].cerrado
    assert entorno["bitacora"][-1][0][1] == "inicio_sesion"
    assert entorno["bitacora"][-1][1]["exito"] is True
