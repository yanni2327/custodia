# -*- coding: utf-8 -*-
"""
Piezas comunes a todas las vistas QML de Custodia.

- `tema_qml()`: los colores del tema actual en un formato que QML entiende.
- `fuente_iconos()`: la fuente de iconos de Windows disponible.
- `logo_url()`: el logo como data URL.
- `ProveedorIconos`: sirve a QML, como ``image://iconos/<nombre>``, los iconos
  que `iconos.py` dibuja por código (carpeta, archivo, avatar, estados…). Así
  las vistas nuevas usan exactamente los mismos dibujos que el resto.
- `preparar_contexto()`: deja todo lo anterior a mano en un contexto QML.
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
from PySide6.QtGui import QColor, QFontDatabase, QGuiApplication, QPixmap
from PySide6.QtQml import QQmlContext, QQmlEngine
from PySide6.QtQuick import QQuickImageProvider

from . import estilo, iconos

#: Carpeta con los archivos .qml.
CARPETA_QML = Path(__file__).resolve().parent / "qml"


def _color(valor: str) -> str:
    """Normaliza un color del tema a #AARRGGBB, que QML entiende siempre."""
    m = re.fullmatch(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", valor)
    if m:
        r, g, b, a = m.groups()
        c = QColor(int(r), int(g), int(b), round(float(a) * 255))
    else:
        c = QColor(valor)
    return c.name(QColor.NameFormat.HexArgb)


def tema_qml() -> dict[str, str]:
    return {k: _color(v) for k, v in estilo.TEMAS[estilo.TEMA_ACTUAL].items()}


def logo_url(lado: int = 128) -> str:
    """El logo (dibujado por código) como data URL para un Image de QML."""
    datos = QByteArray()
    buf = QBuffer(datos)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    iconos.logo(lado).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(datos)).decode()


def fuente_iconos() -> str:
    """Segoe Fluent Icons (Windows 11) o, si no está, Segoe MDL2 (Windows 10)."""
    familias = QFontDatabase.families()
    for nombre in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if nombre in familias:
            return nombre
    return "Segoe UI Symbol"


class ProveedorIconos(QQuickImageProvider):
    """
    ``image://iconos/<nombre>[/<argumento>][?v=N]``

    Nombres: carpeta, archivo, cifrado, avatar/<usuario>, estado/<tipo>.
    El ``?v=N`` no se usa aquí: sirve para que QML pida el icono otra vez al
    cambiar de tema (los colores salen del tema en el momento de dibujar).
    """

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Pixmap)

    def requestPixmap(self, ident: str, size: QSize, pedido: QSize) -> QPixmap:
        ident = ident.split("?", 1)[0]
        nombre, _, arg = ident.partition("/")
        lado = max(pedido.width(), pedido.height(), 0) or 64

        if nombre == "carpeta":
            icono = iconos.icono_carpeta(lado)
        elif nombre == "archivo":
            icono = iconos.icono_archivo(lado)
        elif nombre == "cifrado":
            icono = iconos.icono_archivo_cifrado(lado)
        elif nombre == "avatar":
            icono = iconos.avatar(arg or "?", lado)
        elif nombre == "estado":
            icono = iconos.icono_estado(arg or "info", lado)
        else:
            mapa = QPixmap(lado, lado)
            mapa.fill(QColor(0, 0, 0, 0))
            return mapa
        mapa = icono.pixmap(lado, lado)
        if size is not None:
            size.setWidth(mapa.width())
            size.setHeight(mapa.height())
        return mapa


def preparar_contexto(motor: QQmlEngine, ctx: QQmlContext) -> None:
    """Registra el proveedor de iconos y las propiedades comunes."""
    if motor.imageProvider("iconos") is None:
        motor.addImageProvider("iconos", ProveedorIconos())
    ctx.setContextProperty("T", tema_qml())
    ctx.setContextProperty("oscuro", estilo.TEMA_ACTUAL == "oscuro")
    ctx.setContextProperty("fuente", QGuiApplication.font().family())
    ctx.setContextProperty("iconos", fuente_iconos())
    ctx.setContextProperty("logoUrl", logo_url())


def actualizar_tema(ctx: QQmlContext) -> None:
    """Tras cambiar de tema: QML reevalúa todo lo que dependa de T."""
    ctx.setContextProperty("T", tema_qml())
    ctx.setContextProperty("oscuro", estilo.TEMA_ACTUAL == "oscuro")
