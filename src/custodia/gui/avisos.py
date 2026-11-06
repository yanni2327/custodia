# -*- coding: utf-8 -*-
"""
Diálogos propios de la aplicación.

Reemplazan los cuadros nativos de Qt (`QMessageBox`), que arrastran el aspecto
del sistema y rompen la coherencia visual del programa. Cada aviso lleva su
insignia de color según el tipo —información, éxito, advertencia, error,
pregunta—, una jerarquía clara entre título y mensaje, y un fundido breve al
abrir. Las acciones destructivas usan un botón rojo, distinto del principal.

Las funciones de ayuda imitan la API de QMessageBox para que la sustitución en
el resto del código sea directa:

    avisos.info(self, "Título", "Mensaje")
    if avisos.confirmar(self, "¿Seguro?", "..."): ...
    if avisos.confirmar_peligro(self, "Eliminar", "..."): ...
"""
from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from . import iconos


def _fundir(dialogo: QDialog) -> None:
    """Fundido breve de entrada, compartido por los diálogos propios."""
    dialogo.setWindowOpacity(0.0)
    anim = QPropertyAnimation(dialogo, b"windowOpacity", dialogo)
    anim.setDuration(130)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.start()
    dialogo._anim = anim


class _Aviso(QDialog):
    def __init__(self, parent: QWidget | None, tipo: str, titulo: str,
                 mensaje: str, botones: list[tuple[str, bool, bool]],
                 destructivo: bool = False) -> None:
        super().__init__(parent)
        self.setObjectName("avisoModal")
        self.setModal(True)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(410)
        self.setMaximumWidth(480)
        self._resultado = False

        insignia = QLabel()
        insignia.setPixmap(iconos.icono_aviso(tipo, 44).pixmap(44, 44))
        insignia.setFixedSize(44, 44)

        etiqueta_titulo = QLabel(titulo)
        etiqueta_titulo.setObjectName("avisoTitulo")
        etiqueta_titulo.setWordWrap(True)
        etiqueta_mensaje = QLabel(mensaje)
        etiqueta_mensaje.setObjectName("avisoMensaje")
        etiqueta_mensaje.setWordWrap(True)

        texto = QVBoxLayout()
        texto.setContentsMargins(0, 0, 0, 0)
        texto.setSpacing(5)
        texto.addWidget(etiqueta_titulo)
        texto.addWidget(etiqueta_mensaje)

        fila = QHBoxLayout()
        fila.setSpacing(14)
        fila.addWidget(insignia, 0, Qt.AlignmentFlag.AlignTop)
        fila.addLayout(texto, 1)

        pie = QHBoxLayout()
        pie.addStretch()
        for etiqueta, principal, valor in botones:
            boton = QPushButton(etiqueta)
            if principal:
                boton.setObjectName("principalPeligro" if destructivo else "principal")
            boton.setCursor(Qt.CursorShape.PointingHandCursor)
            boton.clicked.connect(lambda _=False, v=valor: self._terminar(v))
            if principal:
                boton.setDefault(True)
            pie.addWidget(boton)

        columna = QVBoxLayout(self)
        columna.setContentsMargins(24, 22, 24, 18)
        columna.setSpacing(18)
        columna.addLayout(fila)
        columna.addLayout(pie)

    def _terminar(self, valor: bool) -> None:
        self._resultado = valor
        self.accept() if valor else self.reject()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        _fundir(self)


class _Entrada(QDialog):
    """Pide un texto o elige una opción, con el mismo lenguaje visual."""

    def __init__(self, parent: QWidget | None, titulo: str, etiqueta: str,
                 valor: str = "", password: bool = False, descripcion: str = "",
                 opciones: list[str] | None = None, actual: int = 0) -> None:
        super().__init__(parent)
        self.setObjectName("avisoModal")
        self.setModal(True)
        self.setWindowTitle(titulo)
        self.setMinimumWidth(430)
        self._valor: str | None = None

        columna = QVBoxLayout(self)
        columna.setContentsMargins(24, 22, 24, 18)
        columna.setSpacing(12)

        etiqueta_titulo = QLabel(titulo)
        etiqueta_titulo.setObjectName("avisoTitulo")
        etiqueta_titulo.setWordWrap(True)
        columna.addWidget(etiqueta_titulo)

        if descripcion:
            desc = QLabel(descripcion)
            desc.setObjectName("avisoMensaje")
            desc.setWordWrap(True)
            columna.addWidget(desc)

        if etiqueta:
            rotulo = QLabel(etiqueta)
            rotulo.setObjectName("rotulo")
            rotulo.setWordWrap(True)
            columna.addSpacing(2)
            columna.addWidget(rotulo)

        if opciones is not None:
            self.campo: QWidget = QComboBox()
            self.campo.addItems(opciones)
            if 0 <= actual < len(opciones):
                self.campo.setCurrentIndex(actual)
        else:
            self.campo = QLineEdit(valor)
            if password:
                self.campo.setEchoMode(QLineEdit.EchoMode.Password)
            self.campo.selectAll()
        columna.addWidget(self.campo)

        cancelar = QPushButton("Cancelar")
        cancelar.setCursor(Qt.CursorShape.PointingHandCursor)
        cancelar.clicked.connect(self.reject)
        aceptar = QPushButton("Aceptar")
        aceptar.setObjectName("principal")
        aceptar.setDefault(True)
        aceptar.setCursor(Qt.CursorShape.PointingHandCursor)
        aceptar.clicked.connect(self._aceptar)

        pie = QHBoxLayout()
        pie.addStretch()
        pie.addWidget(cancelar)
        pie.addWidget(aceptar)
        columna.addSpacing(6)
        columna.addLayout(pie)

        self.campo.setFocus()

    def _aceptar(self) -> None:
        self._valor = (self.campo.currentText()
                       if isinstance(self.campo, QComboBox) else self.campo.text())
        self.accept()

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        _fundir(self)


# -- API de ayuda (imita a QMessageBox / QInputDialog) ----------------------
#
# Si el padre es la ventana principal (que sabe `preguntar`), el aviso se
# muestra DENTRO de ella, en QML, sobre el contenido desenfocado. Si no (un
# diálogo de widgets todavía sin migrar, o el arranque), se usa el de widgets.

def _anfitrion(parent):
    preguntar = getattr(parent, "preguntar", None)
    return preguntar if callable(preguntar) else None


def _aviso_qml(preguntar, tipo: str, titulo: str, mensaje: str,
               aceptar: str, cancelar: str | None = None,
               peligro: bool = False) -> bool:
    respuesta = preguntar({
        "tipo": tipo, "titulo": titulo, "mensaje": mensaje,
        "aceptar": aceptar, "cancelar": cancelar or "", "peligro": peligro,
    })
    return bool(respuesta and respuesta.get("ok"))


def pedir_texto(parent, titulo: str, etiqueta: str, valor: str = "",
                password: bool = False, descripcion: str = "") -> str | None:
    """Pide un texto. Devuelve lo escrito, o None si se cancela."""
    preguntar = _anfitrion(parent)
    if preguntar:
        r = preguntar({"tipo": "texto", "titulo": titulo, "mensaje": descripcion,
                       "etiqueta": etiqueta, "valor": valor, "password": password,
                       "aceptar": "Aceptar", "cancelar": "Cancelar"})
        return r.get("texto", "") if r and r.get("ok") else None
    dialogo = _Entrada(parent, titulo, etiqueta, valor=valor,
                       password=password, descripcion=descripcion)
    return dialogo._valor if dialogo.exec() else None


def pedir_opcion(parent, titulo: str, etiqueta: str, opciones: list[str],
                 actual: int = 0) -> str | None:
    """Pide elegir una opción de una lista. None si se cancela o está vacía."""
    if not opciones:
        return None
    preguntar = _anfitrion(parent)
    if preguntar:
        r = preguntar({"tipo": "opcion", "titulo": titulo, "mensaje": "",
                       "etiqueta": etiqueta, "opciones": opciones,
                       "actual": actual, "aceptar": "Aceptar",
                       "cancelar": "Cancelar"})
        return r.get("texto") if r and r.get("ok") else None
    dialogo = _Entrada(parent, titulo, etiqueta, opciones=opciones, actual=actual)
    return dialogo._valor if dialogo.exec() else None


def _simple(parent, tipo: str, titulo: str, mensaje: str, boton: str) -> None:
    preguntar = _anfitrion(parent)
    if preguntar:
        _aviso_qml(preguntar, tipo, titulo, mensaje, boton)
        return
    _Aviso(parent, tipo, titulo, mensaje, [(boton, True, True)]).exec()


def mostrar_secreto(parent, titulo: str, mensaje: str, secreto: str) -> None:
    """
    Muestra UNA vez un dato que hay que copiar o dictar (una contraseña
    temporal), con botón para copiarlo. No se guarda en ninguna parte.
    """
    preguntar = _anfitrion(parent)
    if preguntar:
        preguntar({"tipo": "secreto", "titulo": titulo, "mensaje": mensaje,
                   "secreto": secreto, "aceptar": "Listo", "cancelar": ""})
        return
    _Aviso(parent, "info", titulo, f"{mensaje}\n\n{secreto}",
           [("Listo", True, True)]).exec()


def info(parent, titulo: str, mensaje: str) -> None:
    _simple(parent, "info", titulo, mensaje, "Entendido")


def exito(parent, titulo: str, mensaje: str) -> None:
    _simple(parent, "exito", titulo, mensaje, "Listo")


def advertencia(parent, titulo: str, mensaje: str) -> None:
    _simple(parent, "advertencia", titulo, mensaje, "Entendido")


def error(parent, titulo: str, mensaje: str) -> None:
    _simple(parent, "error", titulo, mensaje, "Entendido")


def confirmar(parent, titulo: str, mensaje: str,
              aceptar: str = "Aceptar", cancelar: str = "Cancelar") -> bool:
    preguntar = _anfitrion(parent)
    if preguntar:
        return _aviso_qml(preguntar, "pregunta", titulo, mensaje, aceptar, cancelar)
    dialogo = _Aviso(parent, "pregunta", titulo, mensaje,
                     [(cancelar, False, False), (aceptar, True, True)])
    dialogo.exec()
    return dialogo._resultado


def confirmar_peligro(parent, titulo: str, mensaje: str,
                      aceptar: str = "Eliminar", cancelar: str = "Cancelar") -> bool:
    preguntar = _anfitrion(parent)
    if preguntar:
        return _aviso_qml(preguntar, "error", titulo, mensaje, aceptar, cancelar,
                          peligro=True)
    dialogo = _Aviso(parent, "error", titulo, mensaje,
                     [(cancelar, False, False), (aceptar, True, True)],
                     destructivo=True)
    dialogo.exec()
    return dialogo._resultado
