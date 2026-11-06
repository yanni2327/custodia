# -*- coding: utf-8 -*-
"""
Inicio de sesión.

Quien valida las credenciales es Windows, no esta ventana. El diálogo solo
recoge el usuario y la contraseña y se los pasa a `LogonUser`; si el sistema
devuelve un token, la sesión se abre.

Detalle deliberado: cuando las credenciales fallan, el mensaje no distingue
entre "ese usuario no existe" y "la contraseña es incorrecta". Distinguirlos
permitiría averiguar qué cuentas existen en la máquina probando nombres.

La estética sigue la del resto de la aplicación: una tarjeta sobria, centrada,
con el logo y los campos etiquetados. Toma el tema (claro u oscuro) que ya haya
fijado la aplicación antes de mostrarse.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QWidget,
)

from . import avisos, iconos
from ..core.errors import AuthenticationError, SegundoFactorRequerido
from .sesion import Sesion


class DialogoIngreso(QDialog):
    """Pide credenciales y deja la sesión abierta en `self.sesion`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sesion: Sesion | None = None

        self.setWindowTitle("Custodia")
        self.setObjectName("ingreso")
        self.setModal(True)
        self.setFixedWidth(430)

        # Logo centrado.
        logo = iconos.Logo(52)
        fila_logo = QHBoxLayout()
        fila_logo.addStretch()
        fila_logo.addWidget(logo)
        fila_logo.addStretch()

        titulo = QLabel("Custodia")
        titulo.setObjectName("tituloIngreso")
        titulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        subtitulo = QLabel(
            "Entra con tu cuenta de Windows. Los permisos sobre los archivos "
            "son los que el sistema tenga asignados a esa cuenta."
        )
        subtitulo.setObjectName("subtituloIngreso")
        subtitulo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        subtitulo.setWordWrap(True)

        self.campo_usuario = QLineEdit()
        self.campo_usuario.setPlaceholderText("Nombre de la cuenta")
        self.campo_password = QLineEdit()
        self.campo_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.campo_password.setPlaceholderText("Contraseña")

        self.aviso = QLabel()
        self.aviso.setObjectName("aviso")
        self.aviso.setWordWrap(True)
        self.aviso.hide()

        self.boton_entrar = QPushButton("Entrar")
        self.boton_entrar.setObjectName("principal")
        self.boton_entrar.setDefault(True)
        self.boton_entrar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.boton_entrar.clicked.connect(self._entrar)

        boton_salir = QPushButton("Salir")
        boton_salir.setCursor(Qt.CursorShape.PointingHandCursor)
        boton_salir.clicked.connect(self.reject)

        disposicion = QVBoxLayout(self)
        disposicion.setContentsMargins(40, 36, 40, 30)
        disposicion.setSpacing(14)
        disposicion.addLayout(fila_logo)
        disposicion.addSpacing(2)
        disposicion.addWidget(titulo)
        disposicion.addWidget(subtitulo)
        disposicion.addSpacing(10)
        disposicion.addWidget(self._campo("Usuario", self.campo_usuario))
        disposicion.addWidget(self._campo("Contraseña", self.campo_password))
        disposicion.addWidget(self.aviso)
        disposicion.addSpacing(4)
        disposicion.addWidget(self.boton_entrar)
        disposicion.addWidget(boton_salir)

        self.campo_usuario.setFocus()

    @staticmethod
    def _campo(rotulo: str, campo: QWidget) -> QWidget:
        """Un campo con su etiqueta encima, al estilo del resto de formularios."""
        caja = QWidget()
        columna = QVBoxLayout(caja)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(5)
        etiqueta = QLabel(rotulo)
        etiqueta.setObjectName("rotulo")
        columna.addWidget(etiqueta)
        columna.addWidget(campo)
        return caja

    def _entrar(self) -> None:
        usuario = self.campo_usuario.text().strip()
        password = self.campo_password.text()

        if not usuario:
            self._avisar("Escribe el nombre de la cuenta.")
            self.campo_usuario.setFocus()
            return

        # Bucle para el segundo factor: el primer intento va sin código; si la
        # cuenta lo tiene activado, `iniciar` avisa con SegundoFactorRequerido,
        # se pide el código y se reintenta con él.
        codigo: str | None = None
        while True:
            self.boton_entrar.setEnabled(False)
            self.boton_entrar.setText("Comprobando…")
            try:
                self.sesion = Sesion.iniciar(usuario, password, codigo=codigo)
            except SegundoFactorRequerido:
                self.boton_entrar.setEnabled(True)
                self.boton_entrar.setText("Entrar")
                codigo = self._pedir_codigo()
                if codigo is None:
                    return
                continue
            except AuthenticationError as exc:
                self.boton_entrar.setEnabled(True)
                self.boton_entrar.setText("Entrar")
                self._avisar(str(exc))
                self.campo_password.clear()
                self.campo_password.setFocus()
                return
            else:
                self.boton_entrar.setEnabled(True)
                self.boton_entrar.setText("Entrar")
                self.accept()
                return

    def _pedir_codigo(self) -> str | None:
        """Pide el código de 6 dígitos del segundo factor. None si se cancela."""
        codigo = avisos.pedir_texto(
            self, "Verificación en dos pasos", "Código de 6 dígitos",
            descripcion="Tu cuenta tiene segundo factor activado. Escribe el "
                        "código de tu app de autenticación."
        )
        if codigo is None:
            return None
        return codigo.strip()

    def _avisar(self, mensaje: str) -> None:
        self.aviso.setText(mensaje)
        self.aviso.show()
