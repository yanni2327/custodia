# -*- coding: utf-8 -*-
"""
Backend de desarrollo: doble de prueba en memoria (RNF-03).

Permite ejercitar la lógica que rodea a los permisos sin crear cuentas de
Windows ni escribir ACL. Útil para iterar rápido y para correr pruebas en una
máquina sin privilegios administrativos.

**No es un modo de funcionamiento de la aplicación.** Nunca se entrega
activado, y la función :func:`custodia.core.permissions.backend_activo` carga el
backend real por defecto justamente para que olvidarse de configurarlo no
active este por accidente.

Reproduce solo lo que el contrato exige, incluida la regla de que una
denegación explícita prevalece sobre cualquier permiso, porque es el
comportamiento canónico de NTFS y las pruebas del contrato lo verifican contra
ambos backends. No intenta replicar la herencia, los privilegios ni los
derechos implícitos del propietario: para eso está el backend real.
"""
from __future__ import annotations

from pathlib import Path

from ..permissions import Accion, BackendPermisos, Sujeto


class BackendMemoria(BackendPermisos):
    """Permisos guardados en un diccionario, sin tocar el sistema operativo."""

    def __init__(self) -> None:
        self._permitidos: dict[tuple[str, str], set[Accion]] = {}
        self._denegados: dict[tuple[str, str], set[Accion]] = {}

    @staticmethod
    def _clave(sujeto: Sujeto, ruta: Path) -> tuple[str, str]:
        return (sujeto.username.lower(), str(Path(ruta)).lower())

    def can(self, sujeto: Sujeto, ruta: Path, accion: Accion) -> bool:
        clave = self._clave(sujeto, ruta)
        if accion in self._denegados.get(clave, set()):
            return False
        return accion in self._permitidos.get(clave, set())

    def permisos_efectivos(self, sujeto: Sujeto, ruta: Path) -> set[Accion]:
        clave = self._clave(sujeto, ruta)
        return self._permitidos.get(clave, set()) - self._denegados.get(clave, set())

    def conceder(self, sujeto: Sujeto, ruta: Path, acciones: set[Accion],
                 *, hereda: bool = True) -> None:
        # `hereda` se acepta por contrato pero no se simula: la herencia es
        # responsabilidad de NTFS y reproducirla aquí daría una falsa sensación
        # de equivalencia entre los dos backends.
        self._permitidos.setdefault(self._clave(sujeto, ruta), set()).update(acciones)

    def denegar(self, sujeto: Sujeto, ruta: Path, acciones: set[Accion]) -> None:
        """Denegación explícita, que prevalece sobre cualquier permiso."""
        self._denegados.setdefault(self._clave(sujeto, ruta), set()).update(acciones)

    def limpiar(self) -> None:
        """Vacía todo lo registrado. Para aislar pruebas entre sí."""
        self._permitidos.clear()
        self._denegados.clear()
