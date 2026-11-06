# -*- coding: utf-8 -*-
"""
Backend de producción: la respuesta la da el kernel.

------------------------------------------------------------------------------
Cómo se le pregunta a Windows
------------------------------------------------------------------------------
La API de Windows expone ``AccessCheck``, una función pensada exactamente para
esto. No se usa aquí porque **pywin32 no la envuelve**: existe en el sistema
operativo pero no está disponible desde Python sin bajar a ``ctypes``, y
hacerlo exigiría construir a mano el descriptor de seguridad en formato
autorrelativo y una estructura ``PRIVILEGE_SET``, con la gestión de memoria que
eso implica.

La alternativa que se usa es más simple y, además, más fiel: se **abre un
manejador** al objeto pidiendo el acceso que interesa, suplantando al usuario.
Si el kernel entrega el manejador, el permiso existe; si responde acceso
denegado, no existe.

Lo importante es que esto no simula la comprobación: **es** la comprobación.
Es el mismo camino de código que recorre Windows cuando la aplicación abre un
archivo de verdad, con la DACL evaluada en orden canónico, los SID de grupo del
token resueltos, las denegaciones aplicadas antes que los permisos y los
privilegios del usuario tenidos en cuenta. ``AccessCheck`` habría sido una
consulta *equivalente* a lo que hace el kernel; abrir el manejador es
literalmente lo que hace.

La consulta no tiene efectos secundarios. Abrir con acceso de escritura y
``OPEN_EXISTING`` no trunca ni modifica nada; abrir con acceso de borrado no
borra. El manejador se cierra de inmediato.
"""
from __future__ import annotations

from pathlib import Path

import ntsecuritycon as con
import win32con
import win32file
import pywintypes

from ..errors import NotFound, PermissionDenied
from ..impersonate import impersonate, is_impersonating
from ..permissions import Accion, BackendPermisos, Sujeto

_ERROR_FILE_NOT_FOUND = 2
_ERROR_PATH_NOT_FOUND = 3
_ERROR_ACCESS_DENIED = 5
_ERROR_SHARING_VIOLATION = 32

#: Derechos de directorio que ntsecuritycon no siempre expone. Valores de
#: `winnt.h`, estables desde NT.
_FILE_TRAVERSE = getattr(con, "FILE_TRAVERSE", 0x0020)
_FILE_ADD_FILE = getattr(con, "FILE_ADD_FILE", 0x0002)
_FILE_ADD_SUBDIRECTORY = getattr(con, "FILE_ADD_SUBDIRECTORY", 0x0004)

#: Traducción de acciones del dominio a máscaras de acceso de Windows.
_MASCARAS: dict[Accion, int] = {
    Accion.LEER: con.FILE_GENERIC_READ,
    Accion.ESCRIBIR: con.FILE_GENERIC_WRITE,
    Accion.LISTAR: con.FILE_LIST_DIRECTORY | _FILE_TRAVERSE,
    Accion.CREAR: _FILE_ADD_FILE | _FILE_ADD_SUBDIRECTORY,
    Accion.ELIMINAR: con.DELETE,
    Accion.CAMBIAR_PERMISOS: con.WRITE_DAC,
}

#: Acciones que tienen sentido según el tipo de objeto. Sobre un archivo,
#: preguntar por LISTAR o CREAR no significa nada: son derechos de contenedor.
#: (De hecho FILE_LIST_DIRECTORY y FILE_READ_DATA son el mismo bit, y sin este
#: filtro un archivo legible aparecería también como "listable".)
_ACCIONES_DE_ARCHIVO = {
    Accion.LEER, Accion.ESCRIBIR, Accion.ELIMINAR, Accion.CAMBIAR_PERMISOS,
}

#: Compartición amplia: la consulta no debe bloquear a nadie más mientras el
#: manejador está abierto, que son microsegundos pero podrían coincidir.
_COMPARTIR_TODO = (
    win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE
)


class BackendWindows(BackendPermisos):
    """Implementación que deja cada decisión en manos del kernel."""

    @staticmethod
    def _validar(sujeto: Sujeto, ruta: Path) -> None:
        """
        Comprobaciones previas, en este orden por un motivo.

        La guardia de suplantación va primero porque las demás tocan el disco:
        si ya estuviéramos suplantando, ``exists()`` se ejecutaría con la
        identidad del usuario y podría fallar con acceso denegado antes de
        llegar a la comprobación que explica el verdadero problema.
        """
        if is_impersonating():
            raise RuntimeError(
                "can() no debe llamarse dentro de una suplantación. El token "
                "del usuario va como argumento y el propio método suplanta lo "
                "justo para hacer la consulta; anidar suplantaciones dejaría "
                "el hilo en un estado que no se puede revertir con seguridad."
            )
        if sujeto.token is None:
            raise ValueError(
                f"El sujeto '{sujeto.username}' no trae token. El backend de "
                "Windows necesita el token que devolvió LogonUser: sin él no "
                "hay a quién preguntarle al kernel."
            )
        if not Path(ruta).exists():
            raise NotFound(f"No existe: {Path(ruta).name}")

    @staticmethod
    def _intentar_abrir(ruta: Path, mascara: int, es_carpeta: bool) -> bool:
        """
        Pide un manejador con el acceso indicado. True si el kernel lo concede.

        Se ejecuta ya dentro de la suplantación.
        """
        # Para abrir un manejador a un DIRECTORIO hace falta esta bandera; sin
        # ella, CreateFile solo sabe abrir archivos y falla con acceso denegado
        # aunque los permisos estén bien, lo que daría un falso negativo.
        banderas = win32con.FILE_FLAG_BACKUP_SEMANTICS if es_carpeta else 0

        try:
            manejador = win32file.CreateFile(
                str(ruta),
                mascara,
                _COMPARTIR_TODO,
                None,
                win32con.OPEN_EXISTING,   # nunca crea ni trunca
                banderas,
                None,
            )
        except pywintypes.error as exc:
            if exc.winerror == _ERROR_ACCESS_DENIED:
                return False
            if exc.winerror in (_ERROR_FILE_NOT_FOUND, _ERROR_PATH_NOT_FOUND):
                raise NotFound(f"No existe: {Path(ruta).name}") from exc
            if exc.winerror == _ERROR_SHARING_VIOLATION:
                # Otro proceso lo tiene abierto en exclusiva. No es una
                # respuesta sobre permisos, así que no se finge una.
                raise PermissionDenied(
                    f"'{Path(ruta).name}' está en uso por otro proceso y no se "
                    "pudo comprobar el permiso"
                ) from exc
            raise

        manejador.Close()
        return True

    def can(self, sujeto: Sujeto, ruta: Path, accion: Accion) -> bool:
        """Le pregunta al kernel si concedería este acceso a este usuario."""
        ruta = Path(ruta)
        self._validar(sujeto, ruta)

        # Se resuelve ANTES de suplantar. Dentro del bloque solo debe ocurrir
        # la operación que se quiere someter a los permisos del usuario:
        # consultar metadatos allí dentro se ejecutaría con su identidad y
        # fallaría con acceso denegado sobre cualquier archivo que no pueda
        # leer, que es justamente el caso que se está comprobando.
        es_carpeta = ruta.is_dir()

        if not es_carpeta and accion not in _ACCIONES_DE_ARCHIVO:
            return False   # LISTAR o CREAR sobre un archivo: no aplica

        with impersonate(sujeto.token):
            return self._intentar_abrir(ruta, _MASCARAS[accion], es_carpeta)

    def permisos_efectivos(self, sujeto: Sujeto, ruta: Path) -> set[Accion]:
        """
        Todas las acciones permitidas sobre una ruta (RF-07).

        Se suplanta una sola vez y se sondean todas las acciones dentro del
        mismo bloque, en lugar de llamar a :meth:`can` en bucle: cada entrada y
        salida de la suplantación tiene un coste, y este método lo invoca la
        interfaz cada vez que el usuario selecciona un elemento.
        """
        ruta = Path(ruta)
        self._validar(sujeto, ruta)

        es_carpeta = ruta.is_dir()
        candidatas = _MASCARAS if es_carpeta else {
            a: m for a, m in _MASCARAS.items() if a in _ACCIONES_DE_ARCHIVO
        }

        with impersonate(sujeto.token):
            return {
                accion
                for accion, mascara in candidatas.items()
                if self._intentar_abrir(ruta, mascara, es_carpeta)
            }

    def conceder(self, sujeto: Sujeto, ruta: Path, acciones: set[Accion],
                 *, hereda: bool = True) -> None:
        """Escribe los ACE correspondientes en la DACL del objeto."""
        from .. import acl

        mascara = 0
        for accion in acciones:
            mascara |= _MASCARAS[accion]

        acl.conceder(ruta, sujeto.username, mascara, hereda_a_hijos=hereda)
