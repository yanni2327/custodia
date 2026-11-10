# -*- coding: utf-8 -*-
"""
Clave de recuperación del cifrado por usuario (control C20).

Permite devolver sus archivos a quien perdió la contraseña, sin dejar en este
equipo nada con lo que un administrador local pueda leerlos. La pública queda
aquí; la privada solo existe en un archivo `.custodiarec`, cifrado con una
contraseña propia, que guarda el dueño del computador en una USB.

Quien tenga ese archivo y su contraseña puede leer todos los archivos. Esa es
la razón para que lo custodie una sola persona y no se quede conectado.

Formato: la cabecera de :mod:`respaldo` con otra magia, y como contenido la
clave privada RSA-3072 en PKCS#8.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from . import boveda, config, fsops, respaldo
from .errors import RespaldoError
from .impersonate import impersonate

MAGIA = b"CUSTRECV"
EXTENSION = ".custodiarec"
_TAM_MAXIMO = 16 * 1024


@dataclass
class Resumen:
    recuperados: int = 0
    #: Archivos de esa persona sin sobre de recuperación.
    omitidos: int = 0
    fallidos: int = 0


class ClaveRecuperacion:
    """La privada de la USB, abierta en memoria. Su `repr` no la muestra."""

    __slots__ = ("_privada",)

    def __init__(self, privada) -> None:
        self._privada = privada

    def __repr__(self) -> str:
        return "ClaveRecuperacion(<oculta>)"


def crear(password: str, destino: Path | str) -> None:
    """
    Genera la clave y guarda la privada en `destino`.

    La pública solo se registra si el archivo quedó bien escrito: un equipo con
    pública y sin una privada legible cifraría para una clave que nadie tiene.
    """
    if boveda.recuperacion_configurada():
        raise RespaldoError("Este equipo ya tiene una clave de recuperación.",
                            "ya existe una clave de recuperación")
    error = respaldo.regla_contrasena(password)
    if error:
        raise RespaldoError(error, "contraseña de recuperación demasiado corta")
    destino = Path(destino)
    respaldo.validar_destino(destino)

    privada = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    der = privada.private_bytes(serialization.Encoding.DER,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    respaldo.escribir_verificado(destino, respaldo.sellar_datos(MAGIA, der, password))
    boveda.configurar_recuperacion(privada.public_key())


def abrir(origen: Path | str, password: str) -> ClaveRecuperacion:
    """
    Descifra el archivo de la USB y comprueba que sea el de este equipo.

    :raises RespaldoError: archivo ilegible o ajeno, o contraseña incorrecta.
    """
    ruta = Path(origen)
    try:
        if ruta.stat().st_size > _TAM_MAXIMO:
            raise RespaldoError("Ese archivo no es una clave de recuperación.",
                                "formato no reconocido")
        datos = ruta.read_bytes()
    except OSError as exc:
        raise RespaldoError("No se pudo leer el archivo de recuperación.",
                            "no se pudo leer el archivo") from exc

    der = respaldo.abrir_datos(MAGIA, datos, password)
    try:
        privada = serialization.load_der_private_key(der, password=None)
    except ValueError as exc:
        raise RespaldoError("Ese archivo no es una clave de recuperación.",
                            "formato no reconocido") from exc

    if boveda.huella(privada) != boveda.huella_recuperacion():
        raise RespaldoError(
            "Esta clave no corresponde a la registrada en este equipo. Si es la "
            "correcta, el almacén de identidades fue modificado.",
            "la clave no corresponde a la del equipo",
        )
    return ClaveRecuperacion(privada)


def _recuperar_archivo(ruta: Path, usuario: str, clave: ClaveRecuperacion,
                       publica, token, resumen: Resumen) -> None:
    with impersonate(token):
        blob = fsops.leer(ruta, descifrar=False)
    if not boveda.es_sobre(blob) or usuario not in boveda.destinatarios(blob):
        return
    if not boveda.tiene_sobre_de_recuperacion(blob):
        resumen.omitidos += 1
        return
    nuevo = boveda.reenvolver_desde_recuperacion(blob, usuario, clave._privada, publica)
    with impersonate(token):
        fsops.escribir(ruta, nuevo, sobrescribir=True, cifrar=False)
    resumen.recuperados += 1


def recuperar_cuenta(clave: ClaveRecuperacion, usuario: str, token) -> Resumen:
    """
    Devuelve a `usuario` el acceso a sus archivos, con su identidad nueva.

    Corre con el token del administrador, que tiene acceso NTFS. Si algún
    archivo falla, la cuenta sigue marcada para poder repetir la operación.
    """
    usuario = usuario.lower()
    if not boveda.pendiente_recuperacion(usuario):
        raise RespaldoError(
            "Esa cuenta no tiene nada que recuperar: primero debe entrar con su "
            "contraseña nueva.",
            "la cuenta no está pendiente de recuperación",
        )
    publica = boveda.publica_de(usuario)

    resumen = Resumen()
    for carpeta, _, nombres in os.walk(config.STORAGE_ROOT):
        for nombre in nombres:
            try:
                _recuperar_archivo(Path(carpeta) / nombre, usuario, clave, publica,
                                   token, resumen)
            except Exception:
                resumen.fallidos += 1

    if resumen.fallidos == 0:
        boveda.marcar_recuperada(usuario)
    return resumen
