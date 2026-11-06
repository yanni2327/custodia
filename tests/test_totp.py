# -*- coding: utf-8 -*-
"""
Pruebas del segundo factor (TOTP).

No tocan Windows ni la cuenta: TOTP es aritmética pura, así que se puede
verificar contra el vector oficial del RFC 6238.
"""
from __future__ import annotations

import base64

from custodia.core import totp

#: Secreto del RFC 6238: los bytes ASCII "12345678901234567890" en base32.
_SECRETO = base64.b32encode(b"12345678901234567890").decode().rstrip("=")


def test_vector_oficial_rfc6238():
    # El RFC publica 94287082 (8 dígitos) a T=59s; a 6 dígitos son los últimos
    # seis: 287082. Que coincida demuestra que el HMAC-SHA1 y el truncado son
    # correctos.
    assert totp.codigo_actual(_SECRETO, 59) == "287082"


def test_ventana_tolera_un_paso_de_desfase():
    assert totp.verificar(_SECRETO, "287082", momento=59)        # mismo paso
    assert totp.verificar(_SECRETO, "287082", momento=88)        # +1 paso: sí
    assert not totp.verificar(_SECRETO, "287082", momento=120)   # +2 pasos: no


def test_rechaza_codigos_invalidos():
    s = totp.generar_secreto()
    assert not totp.verificar(s, "abc")
    assert not totp.verificar(s, "")
    assert not totp.verificar(s, None)


def test_un_secreto_verifica_su_propio_codigo():
    s = totp.generar_secreto()
    assert totp.verificar(s, totp.codigo_actual(s))


def test_contador_identifica_el_codigo_aceptado():
    # 287082 es el código del paso 1 (T=30..59). Aceptado desde el paso 2 por
    # la tolerancia de desfase, el contador sigue siendo 1: así se puede saber
    # si ese mismo código ya se usó.
    assert totp.contador_valido(_SECRETO, "287082", momento=59) == 1
    assert totp.contador_valido(_SECRETO, "287082", momento=88) == 1
    assert totp.contador_valido(_SECRETO, "287082", momento=120) is None
    assert totp.contador_valido(_SECRETO, "28708", momento=59) is None   # 5 dígitos


def test_uri_otpauth_bien_formada():
    s = totp.generar_secreto()
    uri = totp.uri_otpauth(s, "ana")
    assert uri.startswith("otpauth://totp/Custodia:ana?secret=")
    assert f"secret={s}" in uri
    assert "period=30" in uri and "digits=6" in uri
