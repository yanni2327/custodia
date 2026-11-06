# -*- coding: utf-8 -*-
"""
Contrato de permisos (RNF-03, RF-07).

Expone una única pregunta —``can(sujeto, ruta, acción)``— resuelta por
implementaciones intercambiables. El resto de la aplicación no sabe cuál está
activa.

------------------------------------------------------------------------------
La tensión que resuelve este módulo
------------------------------------------------------------------------------
Un contrato ``can()`` podría parecer una vuelta atrás. La justificación del
proyecto critica precisamente las aplicaciones que evalúan permisos con reglas
propias, y a primera vista esto es una función que responde si un usuario puede
hacer algo. Si estuviera implementada con condicionales sobre una tabla, sería
exactamente el enfoque que se critica.

No lo es, porque el backend de producción no evalúa nada. Suplanta al usuario
y le pide al kernel un manejador con el acceso que interesa: si Windows lo
concede, el permiso existe. No es una réplica de la comprobación del sistema,
es la comprobación del sistema, hecha por adelantado en vez de descubierta al
fallar. Abrir un manejador con acceso de escritura no escribe nada y con acceso
de borrado no borra, así que la consulta no tiene efectos.

Esa consulta anticipada es lo que permite cumplir el RF-07: para pintar en la
interfaz qué puede hacer el usuario sobre un archivo hay que preguntarlo antes,
no intentar la operación para ver si falla.

------------------------------------------------------------------------------
Dos caminos, un solo criterio
------------------------------------------------------------------------------
La aplicación tiene entonces dos maneras de llegar al mismo veredicto:

- ``fsops`` **intenta** la operación bajo suplantación y traduce el error.
- ``permissions.can()`` **sondea** por adelantado abriendo un manejador.

Ambas terminan en el mismo componente del sistema operativo, así que no pueden
contradecirse. La primera es la que autoriza de verdad —nunca se confía en la
segunda para decidir—; la segunda existe para informar a la interfaz. El orden
importa: ``can()`` nunca sustituye al intento real, porque entre la consulta y
la operación los permisos podrían cambiar.

------------------------------------------------------------------------------
El backend de desarrollo
------------------------------------------------------------------------------
El RNF-03 pide poder ejecutar el núcleo sin permisos reales de Windows. Ese
backend es un **doble de prueba**: sirve para probar la lógica que rodea a los
permisos sin crear cuentas ni tocar ACL. No es un modo de funcionamiento de la
aplicación y nunca se entrega activado. Conviene la distinción: un doble de
prueba sustituye una dependencia durante un test, mientras que el enfoque que
la propuesta critica es implementar el control de acceso real con reglas
propias.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable


class Accion(str, Enum):
    """Operaciones sobre las que se puede preguntar."""

    LEER = "leer"
    ESCRIBIR = "escribir"
    LISTAR = "listar"                    # ver el contenido de una carpeta
    CREAR = "crear"                      # crear dentro de una carpeta
    ELIMINAR = "eliminar"
    CAMBIAR_PERMISOS = "cambiar_permisos"

    def __str__(self) -> str:
        return self.value


@dataclass
class Sujeto:
    """
    Quién pregunta.

    Lleva el nombre y, en el backend real, el token de acceso que Windows
    devolvió al autenticarlo. El token es lo que hace posible que responda el
    kernel: contiene el SID del usuario, los de sus grupos y sus privilegios,
    tal como los calculó Windows al iniciar la sesión.
    """

    username: str
    token: object | None = None


@runtime_checkable
class BackendPermisos(Protocol):
    """Contrato que toda implementación debe cumplir."""

    def can(self, sujeto: Sujeto, ruta: Path, accion: Accion) -> bool:
        """¿Puede este sujeto realizar esta acción sobre esta ruta?"""
        ...

    def permisos_efectivos(self, sujeto: Sujeto, ruta: Path) -> set[Accion]:
        """Todas las acciones permitidas. Para el panel de la interfaz (RF-07)."""
        ...

    def conceder(self, sujeto: Sujeto, ruta: Path, acciones: set[Accion],
                 *, hereda: bool = True) -> None:
        """Otorga permisos. Operación administrativa."""
        ...


_backend: BackendPermisos | None = None


def usar_backend(backend: BackendPermisos) -> None:
    """Instala el backend activo. Se llama una vez al arrancar."""
    global _backend
    _backend = backend


def backend_activo() -> BackendPermisos:
    """
    Devuelve el backend instalado, cargando el de Windows por defecto.

    El de producción es el predeterminado a propósito: si alguien olvida
    configurar el backend, la aplicación usa el real y no el doble de prueba.
    Equivocarse hacia el lado seguro importa cuando lo que está en juego es el
    control de acceso.
    """
    global _backend
    if _backend is None:
        from .backends.windows import BackendWindows
        _backend = BackendWindows()
    return _backend


def can(sujeto: Sujeto, ruta: Path, accion: Accion) -> bool:
    """
    Pregunta si un sujeto puede realizar una acción sobre una ruta.

    Nunca se usa para autorizar: quien autoriza es el intento real bajo
    suplantación en :mod:`fsops`. Esto informa a la interfaz.
    """
    return backend_activo().can(sujeto, ruta, accion)


def permisos_efectivos(sujeto: Sujeto, ruta: Path) -> set[Accion]:
    """Conjunto de acciones permitidas sobre una ruta (RF-07)."""
    return backend_activo().permisos_efectivos(sujeto, ruta)


def conceder(sujeto: Sujeto, ruta: Path, acciones: set[Accion],
             *, hereda: bool = True) -> None:
    """Otorga permisos a un sujeto sobre una ruta."""
    backend_activo().conceder(sujeto, ruta, acciones, hereda=hereda)
