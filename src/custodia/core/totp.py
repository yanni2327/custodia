# -*- coding: utf-8 -*-
"""
Segundo factor basado en tiempo (TOTP, RFC 6238).

Es el mismo mecanismo de Google Authenticator, Authy o Microsoft Authenticator:
un secreto compartido y la hora actual producen un código de seis dígitos que
cambia cada 30 segundos. El servidor y la app calculan el mismo número sin
hablarse, porque ambos parten del secreto y del reloj.

Se implementa a mano, con la biblioteca estándar, por la misma razón que los
iconos se dibujan por código: no añadir una dependencia que haya que empaquetar.
Son unas pocas líneas de HMAC-SHA1 y no hay mérito en ocultarlas tras un paquete.

Honestidad sobre su alcance: el secreto se guarda protegido (DPAPI + ACL), pero
un atacante que ya ejecuta código con privilegios en esta máquina podría leerlo
y calcular códigos, igual que podría con la clave maestra. El segundo factor
sube el listón contra el robo de la contraseña, no contra el dueño de la máquina.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote

PASO = 30         # segundos que dura cada código
DIGITOS = 6


def generar_secreto(longitud: int = 20) -> str:
    """Un secreto nuevo, en base32 (lo que piden las apps de autenticación)."""
    return base64.b32encode(os.urandom(longitud)).decode("ascii").rstrip("=")


def _hotp(secreto_b32: str, contador: int) -> str:
    """Código HOTP (RFC 4226) para un contador dado."""
    relleno = "=" * (-len(secreto_b32) % 8)
    clave = base64.b32decode(secreto_b32.upper() + relleno)
    resumen = hmac.new(clave, struct.pack(">Q", contador), hashlib.sha1).digest()
    desplazamiento = resumen[-1] & 0x0F
    truncado = struct.unpack_from(">I", resumen, desplazamiento)[0] & 0x7FFFFFFF
    return str(truncado % (10 ** DIGITOS)).zfill(DIGITOS)


def codigo_actual(secreto_b32: str, momento: float | None = None) -> str:
    """El código que corresponde ahora mismo."""
    t = time.time() if momento is None else momento
    return _hotp(secreto_b32, int(t // PASO))


def verificar(secreto_b32: str, codigo: str, momento: float | None = None,
              ventana: int = 1) -> bool:
    """
    Comprueba un código, tolerando ±`ventana` pasos de desfase de reloj.

    La tolerancia existe porque el reloj del teléfono y el del equipo casi nunca
    están perfectamente sincronizados; un paso a cada lado cubre el desfase
    normal sin abrir una ventana peligrosa.
    """
    return contador_valido(secreto_b32, codigo, momento, ventana) is not None


def contador_valido(secreto_b32: str, codigo: str, momento: float | None = None,
                    ventana: int = 1) -> int | None:
    """
    Como `verificar`, pero devuelve el contador (paso de 30 s) del código
    aceptado, o None si no vale.

    Saber QUÉ código se aceptó permite rechazar que se use dos veces: un
    código visto por encima del hombro no debe servir para otra operación
    mientras siga dentro de su ventana de validez (RFC 6238, sección 5.2).
    """
    codigo = (codigo or "").strip().replace(" ", "")
    if not codigo.isdigit() or len(codigo) != DIGITOS:
        return None
    t = time.time() if momento is None else momento
    actual = int(t // PASO)
    for desf in range(-ventana, ventana + 1):
        if hmac.compare_digest(_hotp(secreto_b32, actual + desf), codigo):
            return actual + desf
    return None


def uri_otpauth(secreto_b32: str, usuario: str, emisor: str = "Custodia") -> str:
    """
    El enlace `otpauth://` estándar, para generar un QR o añadirlo a mano.

    Las apps de autenticación entienden este formato; de él sacan el nombre, el
    emisor y el secreto.
    """
    etiqueta = quote(f"{emisor}:{usuario}", safe=":")
    return (
        f"otpauth://totp/{etiqueta}"
        f"?secret={secreto_b32}&issuer={quote(emisor)}"
        f"&algorithm=SHA1&digits={DIGITOS}&period={PASO}"
    )
