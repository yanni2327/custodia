# -*- coding: utf-8 -*-
"""
Bloqueo de la interfaz por inactividad.

Una sesión abierta en un equipo desatendido es una sesión de cualquiera que
pase por delante: puede abrir archivos, exportar copias o cambiar permisos con
la identidad de quien se fue. Este módulo cubre ese hueco con dos piezas:

- :class:`VigilanteInactividad` observa la entrada (ratón y teclado) de toda la
  aplicación y avisa cuando pasa el tiempo configurado sin actividad.
- La pantalla de bloqueo, en ``qml/Bloqueo.qml``: una capa opaca dentro de la
  ventana principal que pide la contraseña. Al ser opaca, el contenido que
  había en pantalla deja de verse en cuanto se bloquea.

La comprobación de la contraseña no la hace la pantalla, sino
`Sesion.desbloquear`, con las mismas reglas que el inicio de sesión (límite de
intentos y segundo factor). Así el bloqueo no se convierte en una puerta
trasera para probar contraseñas sin límite.
"""
from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QObject, QTimer, Signal

#: Eventos que cuentan como "la persona sigue aquí".
_EVENTOS_ACTIVIDAD = {
    QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress,
    QEvent.Type.MouseButtonRelease, QEvent.Type.KeyPress,
    QEvent.Type.Wheel, QEvent.Type.TouchBegin,
}


class VigilanteInactividad(QObject):
    """
    Emite `inactivo` cuando pasan `minutos` sin entrada del usuario.

    No reinicia un temporizador en cada movimiento del ratón (serían cientos de
    reinicios por segundo): solo anota la hora del último evento y un reloj
    revisa cada pocos segundos si se superó el límite.
    """

    inactivo = Signal()

    def __init__(self, minutos: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._limite = minutos * 60
        self._ultima = time.monotonic()
        self._pausado = False

        self._reloj = QTimer(self)
        self._reloj.setInterval(5_000)
        self._reloj.timeout.connect(self._revisar)

    def iniciar(self, app: QObject) -> None:
        if self._limite <= 0:
            return   # bloqueo automático desactivado
        app.installEventFilter(self)
        self._ultima = time.monotonic()
        self._reloj.start()

    def detener(self, app: QObject) -> None:
        self._reloj.stop()
        app.removeEventFilter(self)

    def pausar(self) -> None:
        """Mientras la pantalla está bloqueada no tiene sentido vigilar."""
        self._pausado = True

    def reanudar(self) -> None:
        self._pausado = False
        self._ultima = time.monotonic()

    def eventFilter(self, obj: QObject, evento: QEvent) -> bool:
        if evento.type() in _EVENTOS_ACTIVIDAD:
            self._ultima = time.monotonic()
        return False

    def _revisar(self) -> None:
        if self._pausado:
            return
        if time.monotonic() - self._ultima >= self._limite:
            self.inactivo.emit()
