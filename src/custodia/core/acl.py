# -*- coding: utf-8 -*-
"""
Listas de control de acceso de NTFS.

Aquí se administran los permisos reales. Lo que este módulo escribe es
exactamente lo que aparece en Propiedades → Seguridad del Explorador de
Windows, y lo que el kernel consulta en cada apertura de archivo.

Vocabulario mínimo:

- **SID**: identificador único de un usuario o grupo. Windows nunca compara
  nombres, compara SIDs. Renombrar una cuenta no cambia sus permisos.
- **DACL**: la lista de permisos de un objeto. Una secuencia ordenada de ACEs.
- **ACE**: una entrada. Dice "a este SID, permitir/denegar estos accesos".
- **Herencia**: un ACE marcado como heredable se propaga a los hijos. Es lo
  mismo que el ``applies_to_children`` del proyecto anterior, pero implementado
  por NTFS en vez de por un bucle en Python.

Orden canónico: Windows evalúa la DACL de arriba abajo y **se detiene en la
primera coincidencia**. Por eso los ACEs de denegación van siempre antes que
los de permiso. :func:`establecer_permisos` los ordena así automáticamente; si
se escriben al revés, un "permitir" podría ganarle a un "denegar" y el resultado
sería distinto del que muestra la interfaz.
"""
from __future__ import annotations

import contextlib
import threading
from dataclasses import dataclass
from enum import IntFlag
from pathlib import Path
from typing import Iterator

import ntsecuritycon as con
import win32api
import win32security
import pywintypes

from .errors import AccountError, NotFound, PermissionDenied

_ERROR_ACCESS_DENIED = 5
_ERROR_INVALID_OWNER = 1307     # el token no puede asignar a ese propietario

#: Privilegio que permite poner como propietario a otra cuenta.
_SE_RESTORE = "SeRestorePrivilege"

#: El privilegio se activa en el token de todo el proceso: dos hilos no deben
#: solaparse, o el primero en terminar se lo quitaría al otro a media operación.
_lock_privilegio = threading.Lock()


class Perm(IntFlag):
    """
    Permisos de la aplicación, mapeados a máscaras de acceso de Windows.

    Se exponen estos cinco en lugar de las decenas de bits que define NTFS
    porque son los que la interfaz necesita y equivalen a los del modelo
    anterior del proyecto (P_READ, P_WRITE, P_EXEC, P_DELETE, P_LIST).
    """

    LEER = con.FILE_GENERIC_READ
    ESCRIBIR = con.FILE_GENERIC_WRITE
    EJECUTAR = con.FILE_GENERIC_EXECUTE      # en carpetas: atravesar
    ELIMINAR = con.DELETE
    LISTAR = con.FILE_LIST_DIRECTORY
    TOTAL = con.FILE_ALL_ACCESS


#: Marcas de ACE.
#:
#: Se definen con respaldo porque `ntsecuritycon` no expone todas las
#: constantes en todas las versiones de pywin32: `INHERITED_ACE` falta en
#: varias. Son valores fijos de `winnt.h`, idénticos en todas las versiones de
#: Windows desde NT, así que escribirlos a mano es seguro.
_OBJECT_INHERIT_ACE = getattr(con, "OBJECT_INHERIT_ACE", 0x01)       # lo heredan los archivos
_CONTAINER_INHERIT_ACE = getattr(con, "CONTAINER_INHERIT_ACE", 0x02)  # lo heredan las carpetas
_NO_PROPAGATE_INHERIT_ACE = getattr(con, "NO_PROPAGATE_INHERIT_ACE", 0x04)
_INHERIT_ONLY_ACE = getattr(con, "INHERIT_ONLY_ACE", 0x08)
_INHERITED_ACE = getattr(con, "INHERITED_ACE", 0x10)                  # viene del padre

#: Marcas de herencia que aplicamos al crear un ACE heredable.
HEREDA_TODO = _OBJECT_INHERIT_ACE | _CONTAINER_INHERIT_ACE
SIN_HERENCIA = 0


#: SIDs de grupos y cuentas integradas de Windows.
#:
#: Estos identificadores son idénticos en TODAS las instalaciones de Windows,
#: en cualquier idioma. El grupo de administradores es S-1-5-32-544 tanto si la
#: máquina lo muestra como "Administrators" (inglés) como "Administradores"
#: (español) o "Administratoren" (alemán).
#:
#: Por eso nunca buscamos estos principales por nombre: `LookupAccountName(
#: None, "Administrators")` falla con el error 1332 en un Windows en español.
#: Es también la razón por la que Windows guarda SIDs en las ACL y no nombres:
#: renombrar una cuenta no cambia sus permisos.
SIDS_CONOCIDOS = {
    "Administrators":       "S-1-5-32-544",
    "Users":                "S-1-5-32-545",
    "SYSTEM":               "S-1-5-18",
    "Everyone":             "S-1-1-0",
    "Authenticated Users":  "S-1-5-11",
    "CREATOR OWNER":        "S-1-3-0",
}



@dataclass
class Entrada:
    """Un ACE en forma legible para la interfaz."""

    principal: str        # "MAQUINA\\usuario" o "MAQUINA\\grupo"
    sid: str
    permitir: bool        # False = denegar
    mascara: int
    heredado: bool        # viene de la carpeta padre, no se puede editar aquí
    hereda_a_hijos: bool

    @property
    def permisos(self) -> list[str]:
        """Nombres legibles de los permisos que incluye la máscara."""
        nombres = []
        for p in (Perm.LEER, Perm.ESCRIBIR, Perm.EJECUTAR, Perm.ELIMINAR, Perm.LISTAR):
            if self.mascara & p == p:
                nombres.append(p.name)
        if self.mascara & Perm.TOTAL == Perm.TOTAL:
            return ["TOTAL"]
        return nombres


def _sid_de(nombre: str):
    """
    Nombre -> objeto SID.

    Acepta tres formas:
      - un alias de :data:`SIDS_CONOCIDOS` ("Administrators", "SYSTEM"…), que
        se resuelve por SID y por tanto funciona en cualquier idioma de Windows;
      - un SID en texto ("S-1-5-32-544");
      - un nombre de cuenta local ("usuario" o "MAQUINA\\usuario").
    """
    if nombre in SIDS_CONOCIDOS:
        return win32security.ConvertStringSidToSid(SIDS_CONOCIDOS[nombre])

    if nombre.upper().startswith("S-1-"):
        try:
            return win32security.ConvertStringSidToSid(nombre)
        except pywintypes.error as exc:
            raise AccountError(f"SID inválido: '{nombre}'") from exc

    try:
        sid, _, _ = win32security.LookupAccountName(None, nombre)
        return sid
    except pywintypes.error as exc:
        if exc.winerror == 1332:
            raise AccountError(
                f"No existe la cuenta o grupo '{nombre}' en esta máquina. "
                "Si es un grupo integrado de Windows, usa su alias en inglés "
                f"({', '.join(sorted(SIDS_CONOCIDOS))}): se resuelven por SID y "
                "funcionan en cualquier idioma del sistema."
            ) from exc
        raise AccountError(f"No se encontró la cuenta o grupo '{nombre}'") from exc


def sid_conocido(alias: str):
    """Devuelve el objeto SID de un principal integrado de Windows."""
    if alias not in SIDS_CONOCIDOS:
        raise AccountError(f"'{alias}' no es un principal integrado conocido")
    return win32security.ConvertStringSidToSid(SIDS_CONOCIDOS[alias])


def _nombre_de(sid) -> str:
    """SID -> 'DOMINIO\\nombre'. Si el SID ya no existe, devuelve su forma textual."""
    try:
        nombre, dominio, _ = win32security.LookupAccountSid(None, sid)
        return f"{dominio}\\{nombre}" if dominio else nombre
    except pywintypes.error:
        # Cuenta borrada: Windows muestra el SID crudo en este caso, igual que
        # el Explorador cuando aparece una entrada "Cuenta desconocida".
        return win32security.ConvertSidToStringSid(sid)


def leer_permisos(ruta: Path) -> list[Entrada]:
    """
    Devuelve la DACL de un archivo o carpeta.

    Incluye tanto los permisos propios como los heredados de la carpeta padre,
    igual que la pestaña Seguridad del Explorador.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise NotFound(f"No existe: {ruta.name}")

    try:
        sd = win32security.GetNamedSecurityInfo(
            str(ruta),
            win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        )
    except pywintypes.error as exc:
        if exc.winerror == _ERROR_ACCESS_DENIED:
            raise PermissionDenied("Sin permiso para leer los permisos") from exc
        raise

    dacl = sd.GetSecurityDescriptorDacl()
    if dacl is None:
        # DACL nula significa "todo el mundo tiene acceso total". Es distinto de
        # una DACL vacía, que significa lo contrario: nadie tiene acceso.
        return []

    entradas = []
    for i in range(dacl.GetAceCount()):
        (tipo_ace, flags), mascara, sid = dacl.GetAce(i)
        entradas.append(Entrada(
            principal=_nombre_de(sid),
            sid=win32security.ConvertSidToStringSid(sid),
            permitir=tipo_ace in (
                win32security.ACCESS_ALLOWED_ACE_TYPE,
                win32security.ACCESS_ALLOWED_OBJECT_ACE_TYPE,
            ),
            mascara=mascara,
            heredado=bool(flags & _INHERITED_ACE),
            hereda_a_hijos=bool(flags & HEREDA_TODO),
        ))
    return entradas


def establecer_permisos(ruta: Path, entradas: list[tuple[str, int, bool, bool]],
                        *, romper_herencia: bool = False) -> None:
    """
    Reescribe la DACL propia de un archivo o carpeta.

    :param entradas: lista de ``(principal, mascara, permitir, hereda_a_hijos)``.
    :param romper_herencia: si es True, el objeto deja de heredar de su padre y
        solo aplican las entradas dadas. Si es False, estas se suman a las
        heredadas.

    Los ACEs de denegación se colocan primero de forma automática. Ver la nota
    sobre el orden canónico en la cabecera del módulo.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise NotFound(f"No existe: {ruta.name}")

    dacl = win32security.ACL()

    # Primero las denegaciones, después los permisos. Este orden es obligatorio.
    denegar = [e for e in entradas if not e[2]]
    permitir = [e for e in entradas if e[2]]

    for principal, mascara, _, hereda in denegar:
        dacl.AddAccessDeniedAceEx(
            win32security.ACL_REVISION_DS,
            HEREDA_TODO if hereda else SIN_HERENCIA,
            mascara,
            _sid_de(principal),
        )

    for principal, mascara, _, hereda in permitir:
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS,
            HEREDA_TODO if hereda else SIN_HERENCIA,
            mascara,
            _sid_de(principal),
        )

    info = win32security.DACL_SECURITY_INFORMATION
    info |= (
        win32security.PROTECTED_DACL_SECURITY_INFORMATION
        if romper_herencia
        else win32security.UNPROTECTED_DACL_SECURITY_INFORMATION
    )

    try:
        win32security.SetNamedSecurityInfo(
            str(ruta),
            win32security.SE_FILE_OBJECT,
            info,
            None,   # owner: sin cambios
            None,   # group: sin cambios
            dacl,
            None,   # sacl: sin cambios
        )
    except pywintypes.error as exc:
        if exc.winerror == _ERROR_ACCESS_DENIED:
            raise PermissionDenied(
                "Sin permiso para cambiar los permisos. Hace falta ser "
                "propietario del objeto o tener el permiso de cambiar permisos."
            ) from exc
        raise


def conceder(ruta: Path, principal: str, permisos: Perm | int,
             *, hereda_a_hijos: bool = True) -> None:
    """
    Añade un permiso conservando los ya existentes.

    Atajo cómodo sobre :func:`establecer_permisos` para el caso normal de la
    interfaz: "dale lectura a este usuario sobre esta carpeta".
    """
    actuales = [
        (e.principal, e.mascara, e.permitir, e.hereda_a_hijos)
        for e in leer_permisos(ruta)
        if not e.heredado   # los heredados no se copian: se regeneran solos
    ]
    actuales.append((principal, int(permisos), True, hereda_a_hijos))
    establecer_permisos(ruta, actuales)


def denegar(ruta: Path, principal: str, permisos: Perm | int,
            *, hereda_a_hijos: bool = True) -> None:
    """Añade una denegación explícita, que prevalece sobre cualquier permiso."""
    actuales = [
        (e.principal, e.mascara, e.permitir, e.hereda_a_hijos)
        for e in leer_permisos(ruta)
        if not e.heredado
    ]
    actuales.append((principal, int(permisos), False, hereda_a_hijos))
    establecer_permisos(ruta, actuales)


def propietario(ruta: Path) -> str:
    """Nombre del propietario del objeto."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise NotFound(f"No existe: {ruta.name}")
    sd = win32security.GetNamedSecurityInfo(
        str(ruta),
        win32security.SE_FILE_OBJECT,
        win32security.OWNER_SECURITY_INFORMATION,
    )
    return _nombre_de(sd.GetSecurityDescriptorOwner())


@contextlib.contextmanager
def _con_privilegio(nombre: str) -> Iterator[None]:
    """Habilita un privilegio del proceso solo mientras dura el bloque."""
    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY,
    )
    try:
        luid = win32security.LookupPrivilegeValue(None, nombre)
        with _lock_privilegio:
            win32security.AdjustTokenPrivileges(
                token, False, [(luid, win32security.SE_PRIVILEGE_ENABLED)])
            try:
                yield
            finally:
                win32security.AdjustTokenPrivileges(token, False, [(luid, 0)])
    finally:
        token.Close()


def cambiar_propietario(ruta: Path, principal: str) -> None:
    """
    Cambia el propietario. Equivale a ``chown``.

    Poner como propietario a OTRA cuenta exige SeRestorePrivilege habilitado.
    Un proceso elevado lo tiene, pero deshabilitado: se activa solo para esta
    llamada. Sin él, Windows responde con el error 1307. Se ejecuta con la
    identidad de la aplicación, nunca bajo suplantación.
    """
    try:
        with _con_privilegio(_SE_RESTORE):
            win32security.SetNamedSecurityInfo(
                str(Path(ruta)),
                win32security.SE_FILE_OBJECT,
                win32security.OWNER_SECURITY_INFORMATION,
                _sid_de(principal),
                None, None, None,
            )
    except pywintypes.error as exc:
        if exc.winerror in (_ERROR_ACCESS_DENIED, _ERROR_INVALID_OWNER):
            raise PermissionDenied("Sin privilegios para cambiar el propietario") from exc
        raise
