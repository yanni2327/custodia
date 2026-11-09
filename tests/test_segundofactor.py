# -*- coding: utf-8 -*-
"""
Segundo factor por usuario, con DPAPI y ACL reales.

Lo que importa no es que un código correcto entre, sino que el almacén de
secretos falle cerrado: un archivo dañado, un blob ajeno o una cuenta sin
activar nunca deben aceptar un código.
"""
from __future__ import annotations

import base64
import json

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


@pytest.fixture
def almacen_2fa(tmp_path, monkeypatch):
    from custodia.core import config

    ruta = tmp_path / "2fa.dat"
    monkeypatch.setattr(config, "SEGUNDO_FACTOR_FILE", ruta)
    return ruta


def _codigo_erroneo(secreto: str) -> str:
    """Un código de seis dígitos que no vale en ninguna ventana aceptada."""
    from custodia.core import totp

    usados = {totp.codigo_actual(secreto, totp.time.time() + d * totp.PASO)
              for d in (-2, -1, 0, 1, 2)}
    return next(c for c in ("000000", "111111", "222222", "333333", "444444", "555555",
                            "666666") if c not in usados)


@requiere_admin
def test_activar_y_verificar_el_codigo_actual(almacen_2fa):
    from custodia.core import segundofactor, totp

    assert not segundofactor.esta_habilitado("ana")
    secreto, uri = segundofactor.activar("ana")

    assert segundofactor.esta_habilitado("ana")
    assert f"secret={secreto}" in uri and "ana" in uri
    assert segundofactor.verificar("ana", totp.codigo_actual(secreto))
    assert not segundofactor.verificar("ana", _codigo_erroneo(secreto))


@requiere_admin
def test_el_secreto_no_queda_en_claro_y_el_archivo_es_solo_de_admin(almacen_2fa):
    import win32security
    from custodia.core import segundofactor

    secreto, _ = segundofactor.activar("ana")

    assert secreto not in almacen_2fa.read_text("utf-8")
    dacl = win32security.GetNamedSecurityInfo(
        str(almacen_2fa), win32security.SE_FILE_OBJECT,
        win32security.DACL_SECURITY_INFORMATION,
    ).GetSecurityDescriptorDacl()
    sids = {win32security.ConvertSidToStringSid(dacl.GetAce(i)[2])
            for i in range(dacl.GetAceCount())}
    assert sids == {"S-1-5-32-544", "S-1-5-18"}


@requiere_admin
def test_el_nombre_no_distingue_mayusculas(almacen_2fa):
    """Windows no las distingue: «ANA» no puede evadir el segundo factor de «ana»."""
    from custodia.core import segundofactor, totp

    secreto, _ = segundofactor.activar("Ana")
    assert segundofactor.esta_habilitado("ANA")
    assert segundofactor.verificar("aNa", totp.codigo_actual(secreto))


@requiere_admin
def test_verificar_contador_identifica_el_paso_del_codigo(almacen_2fa):
    from custodia.core import segundofactor, totp

    secreto, _ = segundofactor.activar("ana")
    ahora = totp.time.time()
    contador = segundofactor.verificar_contador("ana", totp.codigo_actual(secreto, ahora))

    assert contador is not None and abs(contador - int(ahora // totp.PASO)) <= 1
    assert segundofactor.verificar_contador("ana", _codigo_erroneo(secreto)) is None


@requiere_admin
def test_cuenta_sin_activar_no_acepta_ningun_codigo(almacen_2fa):
    from custodia.core import segundofactor

    assert not segundofactor.verificar("nadie", "123456")
    assert segundofactor.verificar_contador("nadie", "123456") is None


@requiere_admin
def test_desactivar_solo_afecta_a_esa_cuenta(almacen_2fa):
    from custodia.core import segundofactor, totp

    secreto_ana, _ = segundofactor.activar("ana")
    secreto_juan, _ = segundofactor.activar("juan")

    segundofactor.desactivar("ana")

    assert not segundofactor.esta_habilitado("ana")
    assert not segundofactor.verificar("ana", totp.codigo_actual(secreto_ana))
    assert segundofactor.verificar("juan", totp.codigo_actual(secreto_juan))


@requiere_admin
def test_desactivar_una_cuenta_sin_factor_no_escribe(almacen_2fa):
    from custodia.core import segundofactor

    segundofactor.desactivar("nadie")
    assert not almacen_2fa.exists()


@requiere_admin
def test_reactivar_invalida_el_secreto_anterior(almacen_2fa):
    """El caso del teléfono perdido: el secreto viejo deja de servir."""
    from custodia.core import segundofactor, totp

    viejo, _ = segundofactor.activar("ana")
    nuevo, _ = segundofactor.activar("ana")

    assert viejo != nuevo
    assert segundofactor.verificar("ana", totp.codigo_actual(nuevo))
    assert segundofactor.verificar_contador("ana", totp.codigo_actual(viejo)) is None


@requiere_admin
def test_archivo_danado_falla_cerrado(almacen_2fa):
    from custodia.core import segundofactor

    almacen_2fa.write_text("{esto no es json", "utf-8")

    assert not segundofactor.esta_habilitado("ana")
    assert not segundofactor.verificar("ana", "123456")


@requiere_admin
def test_blob_ajeno_falla_cerrado(almacen_2fa):
    """Un blob que DPAPI no abre, como uno copiado de otro equipo."""
    from custodia.core import segundofactor

    falso = base64.b64encode(b"esto no salio de DPAPI").decode("ascii")
    almacen_2fa.write_text(json.dumps({"ana": falso}), "utf-8")

    assert segundofactor.esta_habilitado("ana")
    assert not segundofactor.verificar("ana", "123456")
    assert segundofactor.verificar_contador("ana", "123456") is None


@requiere_admin
def test_confirmar_operacion_de_punta_a_punta(almacen_2fa, bitacora, tmp_path, monkeypatch):
    """Sesion, secreto en DPAPI y contador de intentos, sin dobles."""
    from custodia.core import audit, config, segundofactor, totp
    from custodia.gui.sesion import Sesion

    monkeypatch.setattr(config, "INTENTOS_FILE", tmp_path / "intentos.dat")
    secreto, _ = segundofactor.activar("ana")
    sesion = Sesion(username="ana", token=None, es_admin=False)
    codigo = totp.codigo_actual(secreto)

    assert sesion.confirmar_operacion(_codigo_erroneo(secreto), "eliminar") == "incorrecto"
    assert sesion.confirmar_operacion(codigo, "eliminar") == "ok"
    assert sesion.confirmar_operacion(codigo, "descargar") == "usado"

    audit.flush()
    assert audit.consultar(accion="fallo_segundo_factor")[0]["detalle"] == "eliminar"
    assert audit.consultar(accion="segundo_factor_ok")[0]["detalle"] == "eliminar"
