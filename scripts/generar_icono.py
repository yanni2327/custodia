# -*- coding: utf-8 -*-
"""
Genera el icono del ejecutable (``src/custodia/gui/recursos/custodia.ico``).

El icono sale del mismo código que dibuja el logo en la aplicación
(`iconos.icono_app`), así que nunca se desincroniza con la marca. Hay que
volver a ejecutarlo solo si cambia el logo:

    python scripts\\generar_icono.py

Un .ico de Windows lleva el mismo icono a varios tamaños, uno por cada sitio
donde se muestra (16 px en listas, 32 en el escritorio, 256 en «iconos
grandes»…). Cada tamaño se dibuja aparte en lugar de reducir el grande, para
que los pequeños queden nítidos. Las imágenes van en PNG dentro del .ico,
formato que Windows admite desde Vista.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

TAMANOS = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)
DESTINO = RAIZ / "src" / "custodia" / "gui" / "recursos" / "custodia.ico"


def _png(lado: int) -> bytes:
    from custodia.gui import iconos

    datos = QByteArray()
    buf = QBuffer(datos)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    iconos.icono_app(lado).save(buf, "PNG")
    return bytes(datos)


def generar(destino: Path = DESTINO) -> Path:
    imagenes = [(lado, _png(lado)) for lado in TAMANOS]

    # Cabecera ICONDIR (reservado, tipo 1 = icono, número de imágenes) y una
    # entrada ICONDIRENTRY de 16 bytes por imagen. En las entradas, 0
    # significa 256 en ancho y alto.
    cabecera = struct.pack("<HHH", 0, 1, len(imagenes))
    desplazamiento = len(cabecera) + 16 * len(imagenes)
    entradas, cuerpos = b"", b""
    for lado, png in imagenes:
        medida = 0 if lado >= 256 else lado
        entradas += struct.pack("<BBBBHHII", medida, medida, 0, 0, 1, 32,
                                len(png), desplazamiento)
        desplazamiento += len(png)
        cuerpos += png

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(cabecera + entradas + cuerpos)
    return destino


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    ruta = generar()
    print(f"Icono generado: {ruta} ({ruta.stat().st_size // 1024} KB, "
          f"{len(TAMANOS)} tamaños)")
