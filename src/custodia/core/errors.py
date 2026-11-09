# -*- coding: utf-8 -*-
"""
Excepciones del dominio.

El núcleo nunca lanza excepciones de pywin32 hacia afuera: las traduce a
estas. Así la capa de API puede mapear cada una a un código HTTP sin saber
nada de Windows, y el cliente de escritorio puede mostrar mensajes útiles.
"""
from __future__ import annotations


class CustodiaError(Exception):
    """Base de todos los errores del núcleo."""


class AuthenticationError(CustodiaError):
    """Usuario o contraseña incorrectos, o cuenta deshabilitada/bloqueada."""


class SessionError(CustodiaError):
    """Sesión inexistente, expirada o ya cerrada."""


class SegundoFactorRequerido(CustodiaError):
    """
    La contraseña fue correcta, pero la cuenta tiene segundo factor activado y
    hace falta el código de verificación. No es un error de credenciales: le
    dice a la interfaz que pida el código y reintente.
    """


class CambioDeContrasenaRequerido(CustodiaError):
    """
    La contraseña fue correcta, pero Windows exige cambiarla antes de entrar
    (un administrador la restableció a una temporal, o caducó). No es un error
    de credenciales: le dice a la interfaz que pida una contraseña nueva.
    """


class CuentaBloqueada(AuthenticationError):
    """La cuenta está bloqueada temporalmente por demasiados intentos fallidos."""


class PermissionDenied(CustodiaError):
    """
    Windows denegó la operación.

    Importante: esta excepción NO la decide nuestro código evaluando reglas.
    Se levanta cuando el kernel devuelve ERROR_ACCESS_DENIED mientras estamos
    suplantando al usuario. Es el punto central del proyecto.
    """


class PathOutsideJail(CustodiaError):
    """La ruta solicitada se sale de STORAGE_ROOT."""


class InvalidPathName(CustodiaError):
    """Nombre inválido para Windows (caracteres prohibidos, nombre reservado…)."""


class NotFound(CustodiaError):
    """El archivo o carpeta no existe."""


class AlreadyExists(CustodiaError):
    """Ya existe un elemento con ese nombre."""


class AccountError(CustodiaError):
    """Error al crear, modificar o eliminar una cuenta o grupo de Windows."""


class ProtectedAccount(AccountError):
    """
    Se intentó tocar una cuenta que no pertenece a la aplicación.

    Salvaguarda: sin esto, un bug podría borrar la cuenta del Administrador.
    """


class FileTooLarge(CustodiaError):
    """El contenido supera MAX_FILE_BYTES."""


class CryptoError(CustodiaError):
    """
    Error de cifrado o descifrado.

    Cubre tres casos distintos que conviene no confundir: la clave maestra no
    existe, la clave maestra no se puede descifrar (blob de otra máquina), o el
    contenido del archivo fue alterado y falla la autenticación de GCM.
    """


class RespaldoError(CryptoError):
    """
    Falló la exportación o la restauración del respaldo de la clave maestra.

    `motivo` es un texto fijo apto para la bitácora: nunca incluye la clave, la
    contraseña ni el texto de otra excepción.
    """

    def __init__(self, mensaje: str, motivo: str) -> None:
        super().__init__(mensaje)
        self.motivo = motivo
