# -*- coding: utf-8 -*-
"""
Inicio de sesión con Qt Quick (QML).

Primera pieza de la migración de la interfaz a QML. La lógica no cambia: quien
valida las credenciales sigue siendo Windows, a través de `Sesion.iniciar`,
con el mismo bloqueo por intentos y el mismo segundo factor. Lo que cambia es
la presentación, que vive en ``qml/Login.qml``.

Reparto de responsabilidades:

- **QML** dibuja, anima y valida lo trivial (campos vacíos).
- **PuenteIngreso** (este archivo) es la única puerta entre la vista y el
  núcleo: recibe usuario/contraseña/código y devuelve señales de resultado.
  La vista nunca toca la sesión ni las credenciales más allá de pasarlas.

La autenticación corre en un hilo aparte. `LogonUser` tarda varios segundos
cuando la contraseña es incorrecta (Windows lo hace a propósito para frenar la
fuerza bruta); en el hilo de la interfaz eso congelaría la animación de espera.
El hilo no suplanta a nadie, así que no hay riesgo de que la identidad de un
usuario se quede pegada al hilo de la interfaz.
"""
from __future__ import annotations

import ctypes
import re
import threading

from PySide6.QtCore import QEventLoop, QObject, QUrl, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
# Importar QtQuick registra sus tipos en Python (la raíz llega como
# QQuickWindow y no como QWindow) y hace que PyInstaller empaquete Qt Quick.
from PySide6 import QtQuick  # noqa: F401

from ..core.errors import (AccountError, AuthenticationError,
                           CambioDeContrasenaRequerido, SegundoFactorRequerido)
from .qmlbase import CARPETA_QML, preparar_contexto
from .sesion import Sesion

_QML = CARPETA_QML / "Login.qml"


class PuenteIngreso(QObject):
    """Objeto que QML ve como `puente`."""

    error = Signal(str)
    pideCodigo = Signal()
    #: La contraseña era temporal (o caducó): hay que crear una nueva.
    pideNuevaContrasena = Signal()
    exito = Signal()
    ocupadoCambio = Signal(bool)
    #: Fin del ingreso (con o sin sesión). Termina el bucle de `ejecutar`.
    terminado = Signal()

    #: Uso interno: resultado del hilo de autenticación hacia el hilo de la
    #: interfaz (Qt lo entrega en cola, en el hilo correcto).
    _resultado = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.sesion: Sesion | None = None
        self._usuario = ""
        self._password: str | None = None
        self._ocupado = False
        self._fin = False
        self._resultado.connect(self._al_resultado)

    # -- llamadas desde QML -------------------------------------------------

    @Slot(str, str)
    def entrar(self, usuario: str, password: str) -> None:
        usuario = usuario.strip()
        if not usuario:
            self.error.emit("Escribe el nombre de la cuenta.")
            return
        if not password:
            self.error.emit("Escribe tu contraseña.")
            return
        self._usuario, self._password = usuario, password
        self._intentar(None)

    @Slot(str)
    def verificarCodigo(self, codigo: str) -> None:
        codigo = codigo.strip()
        if not re.fullmatch(r"\d{6}", codigo):
            self.error.emit("El código tiene 6 dígitos.")
            return
        if self._password is None:
            self.error.emit("Vuelve a escribir tu contraseña.")
            return
        self._intentar(codigo)

    @Slot(str, str)
    def cambiarContrasena(self, nueva: str, repetida: str) -> None:
        """Paso obligatorio tras entrar con una contraseña temporal."""
        if self._password is None:
            self.error.emit("Vuelve a escribir tu contraseña temporal.")
            return
        if nueva != repetida:
            self.error.emit("Las dos contraseñas no coinciden.")
            return
        temporal = self._password
        usuario = self._usuario

        def cambiar_y_entrar():
            Sesion.cambiar_contrasena_obligatoria(usuario, temporal, nueva)
            # Desde aquí la contraseña buena es la nueva (también si después
            # se pide el código del segundo factor).
            self._password = nueva
            return Sesion.iniciar(usuario, nueva)

        self._intentar(None, cambiar_y_entrar)

    @Slot()
    def volver(self) -> None:
        """Del paso del código al de la contraseña: se olvida la contraseña."""
        self._password = None

    @Slot(result=bool)
    def mayusculas(self) -> bool:
        """True si Bloq Mayús está activo (aviso típico en un campo de clave)."""
        try:
            return bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        except Exception:
            return False

    @Slot()
    def terminar(self) -> None:
        """QML terminó la animación de salida tras un ingreso correcto."""
        if not self._fin:
            self._fin = True
            self.terminado.emit()

    @Slot()
    def cancelar(self) -> None:
        """La persona cerró la ventana o pulsó Salir."""
        if self._fin:
            return
        self._fin = True
        self._password = None
        self.terminado.emit()

    # -- autenticación en segundo plano -------------------------------------

    def _intentar(self, codigo: str | None, accion=None) -> None:
        if self._ocupado:
            return
        self._ocupado = True
        self.ocupadoCambio.emit(True)
        usuario, password = self._usuario, self._password
        if accion is None:
            accion = lambda: Sesion.iniciar(usuario, password, codigo=codigo)

        def trabajo() -> None:
            try:
                resultado = ("ok", accion())
            except SegundoFactorRequerido:
                resultado = ("codigo", None)
            except CambioDeContrasenaRequerido:
                resultado = ("cambio", None)
            except (AuthenticationError, AccountError) as exc:
                resultado = ("error", str(exc))
            except Exception as exc:   # cualquier fallo inesperado, sin colgar
                resultado = ("error", f"No se pudo iniciar sesión: {exc}")
            self._resultado.emit(resultado)

        threading.Thread(target=trabajo, name="custodia-ingreso",
                         daemon=True).start()

    @Slot(object)
    def _al_resultado(self, resultado: tuple) -> None:
        self._ocupado = False
        self.ocupadoCambio.emit(False)
        tipo, valor = resultado

        if tipo == "ok":
            self._password = None
            if self._fin:
                # Se cerró la ventana mientras se comprobaba: la sesión que
                # llegó tarde no la va a usar nadie, se libera.
                valor.cerrar()
                return
            self.sesion = valor
            self.exito.emit()
        elif tipo == "codigo":
            self.pideCodigo.emit()
        elif tipo == "cambio":
            self.pideNuevaContrasena.emit()
        else:
            self.error.emit(valor)


class VentanaIngreso:
    """
    Muestra el inicio de sesión QML y espera a que termine.

    Uso::

        ingreso = VentanaIngreso()       # RuntimeError si QML no carga
        if ingreso.ejecutar():
            sesion = ingreso.sesion
    """

    def __init__(self) -> None:
        self.puente = PuenteIngreso()
        self.motor = QQmlApplicationEngine()

        ctx = self.motor.rootContext()
        preparar_contexto(self.motor, ctx)
        ctx.setContextProperty("puente", self.puente)

        errores: list[str] = []
        self.motor.warnings.connect(
            lambda lista: errores.extend(e.toString() for e in lista))
        self.motor.load(QUrl.fromLocalFile(str(_QML)))
        raices = self.motor.rootObjects()
        if not raices:
            raise RuntimeError(f"No se pudo cargar {_QML.name}:\n" + "\n".join(errores))
        self.ventana = raices[0]

    @property
    def sesion(self) -> Sesion | None:
        return self.puente.sesion

    def ejecutar(self) -> bool:
        """Bloquea hasta que la persona entra o se va. True si entró."""
        app = QGuiApplication.instance()
        # Al cerrar esta ventana todavía no hay otra abierta; sin esto, Qt
        # podría interpretar que se cerró la última ventana y salir.
        anterior = app.quitOnLastWindowClosed()
        app.setQuitOnLastWindowClosed(False)

        bucle = QEventLoop()
        self.puente.terminado.connect(bucle.quit)
        try:
            self.ventana.show()
            self.ventana.requestActivate()
            bucle.exec()
        finally:
            self.ventana.close()
            app.setQuitOnLastWindowClosed(anterior)
            self.motor.deleteLater()
        return self.puente.sesion is not None
