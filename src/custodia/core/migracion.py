# -*- coding: utf-8 -*-
"""
Migración de archivos con clave maestra (v1) al cifrado por usuario (control C20).

Se hace al entrar cada persona, sobre su carpeta personal, porque entonces su
clave privada está en memoria: envolver para ella no depende de ninguna clave
pública guardada en el equipo.

Regla que no se rompe: un archivo solo se migra si **todos** los que hoy pueden
leerlo seguirán pudiendo. Si lo puede leer un grupo, o alguien que aún no tiene
identidad, se queda en v1 y se vuelve a intentar en el próximo ingreso.

Los administradores no cuentan como lectores: que dejen de poder leer es
justamente el objetivo. `Compartida` no se migra: la abre un grupo entero.

Los bloques del v1 pueden seguir en el disco hasta que se sobrescriban, y un
respaldo `.custodiakey` sigue abriendo cualquier copia antigua del v1.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import ntsecuritycon as con
import pywintypes
import win32security

from . import acl, boveda, config, crypto, espacios, fsops
from .impersonate import impersonate

#: Administradores, SYSTEM y CREATOR OWNER no son lectores que conservar.
_NO_LECTORES = {"S-1-5-32-544", "S-1-5-18", "S-1-3-0"}


@dataclass
class Resumen:
    migrados: int = 0
    pendientes: int = 0
    fallidos: int = 0


def _version(ruta: Path) -> int | None:
    """Versión del formato según la cabecera; None si no está cifrado."""
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(crypto.TAM_CABECERA)
    except OSError:
        return None
    return cabecera[len(crypto.MAGIA)] if crypto.esta_cifrado(cabecera) else None


def _sid_de_administradores_app() -> str | None:
    try:
        sid, _, _ = win32security.LookupAccountName(None, config.ADMIN_GROUP)
    except pywintypes.error:
        return None
    return win32security.ConvertSidToStringSid(sid)


def lectores(ruta: Path) -> dict[str, object] | None:
    """
    {usuario: clave_pública} de quienes pueden leer el archivo.

    None si no se puede garantizar el acceso de todos: lo lee un grupo o una
    cuenta sin identidad.
    """
    excluidos = _NO_LECTORES | {_sid_de_administradores_app()}
    salida: dict[str, object] = {}
    for entrada in acl.leer_permisos(ruta):
        if (not entrada.permitir or entrada.sid in excluidos
                or not entrada.mascara & con.FILE_READ_DATA):
            continue
        try:
            sid = win32security.ConvertStringSidToSid(entrada.sid)
            _, _, tipo = win32security.LookupAccountSid(None, sid)
        except pywintypes.error:
            continue   # cuenta borrada: ya no hay a quién conservarle el acceso
        if tipo != win32security.SidTypeUser:
            return None
        nombre = entrada.principal.rsplit("\\", 1)[-1].lower()
        publica = boveda.publica_de(nombre)
        if publica is None:
            return None
        salida[nombre] = publica
    return salida


def _migrar_v1(ruta: Path, username: str, token, privada) -> bool:
    destinatarios = lectores(ruta)
    if destinatarios is None:
        return False
    destinatarios[username.lower()] = privada.public_key()

    with impersonate(token):
        blob = fsops.leer(ruta, descifrar=False)
    datos = crypto.descifrar(blob)
    nuevo = boveda.cifrar_para(datos, destinatarios)
    # Antes de sustituir nada: lo que se va a escribir se tiene que poder abrir.
    if boveda.descifrar(nuevo, username, privada) != datos:
        raise ValueError("el archivo migrado no coincide con el original")
    with impersonate(token):
        fsops.escribir(ruta, nuevo, sobrescribir=True, cifrar=False)
    return True


def _migrar_v2(ruta: Path, username: str, token, privada) -> bool:
    with impersonate(token):
        blob = fsops.leer(ruta, descifrar=False)
    if username.lower() not in boveda.destinatarios(blob):
        return False
    datos = boveda.descifrar(blob, username, privada)
    nuevo = boveda.actualizar(blob, datos, username, privada,
                              recuperacion=boveda.publica_recuperacion())
    with impersonate(token):
        fsops.escribir(ruta, nuevo, sobrescribir=True, cifrar=False)
    return True


def migrar_espacio(username: str, token, privada, limite: int | None = None) -> Resumen:
    """Migra la carpeta personal, hasta `limite` archivos por ingreso."""
    tope = config.MIGRACION_MAX_POR_INGRESO if limite is None else limite
    resumen = Resumen()
    for carpeta, _, nombres in os.walk(espacios.ruta_personal(username)):
        for nombre in nombres:
            ruta = Path(carpeta) / nombre
            version = _version(ruta)
            if version not in (crypto.VERSION, 2):
                continue
            if resumen.migrados >= tope:
                resumen.pendientes += 1
                continue
            try:
                migrar = _migrar_v1 if version == crypto.VERSION else _migrar_v2
                if migrar(ruta, username, token, privada):
                    resumen.migrados += 1
                else:
                    resumen.pendientes += 1
            except Exception:
                resumen.fallidos += 1
    return resumen


def _en_compartida(ruta: Path) -> bool:
    relativa = ruta.relative_to(config.STORAGE_ROOT).parts
    return bool(relativa) and relativa[0].lower() == espacios.COMPARTIDA.lower()


def pendientes_fuera_de_compartida() -> int:
    """Archivos v1 que aún no se han migrado. Con 0 se puede activar por defecto."""
    total = 0
    for carpeta, _, nombres in os.walk(config.STORAGE_ROOT):
        for nombre in nombres:
            ruta = Path(carpeta) / nombre
            if _version(ruta) == crypto.VERSION and not _en_compartida(ruta):
                total += 1
    return total
