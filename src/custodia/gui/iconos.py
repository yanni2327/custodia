# -*- coding: utf-8 -*-
"""
Logo e iconos, dibujados por código.

Nada de archivos de imagen. Tres razones:

**Escalan.** Se dibujan con vectores, así que se ven igual de nítidos en una
pantalla normal que en una de alta densidad, sin tener que mantener versiones
a 16, 32 y 64 píxeles.

**Siguen la paleta.** Toman los colores de `estilo.py`, de modo que cambiar la
identidad visual es editar un archivo y no reexportar un juego de iconos.

**Se empaquetan solos.** Un recurso externo obliga a declararlo en la receta de
PyInstaller y, en el caso de los SVG, a incluir además el complemento de
imágenes de Qt. Un icono que es código viaja dentro del ejecutable sin que haya
nada que recordar.

Se sustituyen a propósito los iconos del sistema: las carpetas amarillas de
Windows arrastran un estilo de hace veinte años y chocan con cualquier interfaz
moderna.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget

from . import estilo


def _lienzo(lado: int) -> QPixmap:
    """Un mapa de bits transparente listo para dibujar con suavizado."""
    mapa = QPixmap(lado, lado)
    mapa.fill(Qt.GlobalColor.transparent)
    return mapa


def _pintor(mapa: QPixmap) -> QPainter:
    pintor = QPainter(mapa)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    return pintor


def _icono(mapa: QPixmap) -> QIcon:
    """
    Envuelve un mapa en un QIcon que no se tiñe al seleccionar la fila.

    Qt, por defecto, repinta el icono con el color de resalte cuando el
    elemento está seleccionado. Sobre una selección tenue eso lo convierte en
    un bloque de color. Al registrar el mismo mapa para los modos Normal,
    Selected y Active, el icono conserva sus propios colores siempre.
    """
    icono = QIcon()
    icono.addPixmap(mapa, QIcon.Mode.Normal)
    icono.addPixmap(mapa, QIcon.Mode.Selected)
    icono.addPixmap(mapa, QIcon.Mode.Active)
    return icono


def _pluma(pintor: QPainter, color: QColor, grosor: float) -> QPen:
    """Una pluma de trazo fino con extremos y uniones redondeados."""
    pluma = QPen(color, grosor)
    pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
    pintor.setPen(pluma)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    return pluma


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------

#: Cuánto se acortan los dos extremos, como fracción del lado del hexágono.
#: A 0 el hueco es exactamente el lado derecho; subiéndolo se abre más y la
#: letra se lee antes, a costa de que la figura pierda cuerpo.
APERTURA = 0.16


def _trazo_hexagono_abierto(lado: float) -> QPainterPath:
    """
    La silueta del logo: un hexágono al que le falta el lado derecho.

    El detalle que lo decide todo es **cuáles** son los dos extremos. Se
    recorren los seis vértices sin cerrar el camino, de modo que el trazo
    termina en los dos vértices de la derecha, que son espejo uno del otro
    respecto al eje horizontal. Saltarse el vértice derecho —que es lo
    intuitivo si uno piensa "quitar la esquina"— deja los extremos en el
    vértice inferior y en el superior derecho, que no se corresponden: la
    figura sale torcida, con el brazo de arriba más largo y más tumbado que el
    de abajo.
    """
    import math

    centro = QPointF(lado / 2, lado / 2)
    radio = lado * 0.37

    vertices = []
    for i in range(6):
        angulo = math.radians(60 * i - 30)
        vertices.append(QPointF(
            centro.x() + radio * math.cos(angulo),
            centro.y() + radio * math.sin(angulo),
        ))

    # v0 es el vértice superior derecho y v1 el inferior derecho. Se pasa por
    # todos los demás y se termina en v1, dejando sin dibujar el lado v1-v0.
    recorrido = [vertices[0], vertices[5], vertices[4],
                 vertices[3], vertices[2], vertices[1]]

    if APERTURA > 0:
        def _acortar(extremo: QPointF, hacia: QPointF, fraccion: float) -> QPointF:
            return QPointF(
                extremo.x() + (hacia.x() - extremo.x()) * fraccion,
                extremo.y() + (hacia.y() - extremo.y()) * fraccion,
            )

        recorrido[0] = _acortar(vertices[0], vertices[5], APERTURA)
        recorrido[-1] = _acortar(vertices[1], vertices[2], APERTURA)

    trazo = QPainterPath(recorrido[0])
    for punto in recorrido[1:]:
        trazo.lineTo(punto)
    return trazo


def logo(lado: int = 32) -> QPixmap:
    """
    El distintivo de Custodia, con el degradado de la paleta.

    El centrado no es el del hexágono sino el del trazo realmente dibujado.
    La diferencia importa: como el costado derecho está abierto, ahí no hay
    tinta, y una figura centrada en el centro geométrico del hexágono queda
    desplazada a la vista. Se mide el rectángulo que ocupa el trazo, se le
    suma el grosor de la pluma —que sobresale media anchura a cada lado— y se
    encaja eso en el lienzo.
    """
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)

    degradado = QLinearGradient(0, lado, lado, 0)
    degradado.setColorAt(0.0, QColor(estilo.AZUL_CLARO))
    degradado.setColorAt(0.55, QColor(estilo.AZUL))
    degradado.setColorAt(1.0, QColor(estilo.AZUL_HONDO))

    _pintar_logo(pintor, lado, QBrush(degradado), margen_rel=0.06)
    pintor.end()
    return mapa


def _pintar_logo(pintor: QPainter, lado: float, pincel: QBrush,
                 margen_rel: float, desplazamiento: float = 0.0) -> None:
    """
    Dibuja el trazo del logo encajado en un cuadrado de `lado`, con el
    pincel dado (degradado en la app, blanco sobre la ficha del icono).
    `desplazamiento` es la esquina del cuadrado dentro del lienzo.
    """
    grosor = lado * 0.17
    trazo = _trazo_hexagono_abierto(lado)

    # Lo que de verdad ocupa la figura, con el grosor incluido.
    tinta = trazo.boundingRect().adjusted(
        -grosor / 2, -grosor / 2, grosor / 2, grosor / 2
    )

    # Se encaja dejando un margen, y se desplaza para que el centro de la
    # tinta coincida con el centro del cuadrado.
    margen = lado * margen_rel
    disponible = lado - margen * 2
    escala = min(disponible / tinta.width(), disponible / tinta.height())

    pintor.save()
    pintor.translate(desplazamiento + lado / 2, desplazamiento + lado / 2)
    pintor.scale(escala, escala)
    pintor.translate(-tinta.center().x(), -tinta.center().y())

    pluma = QPen(pincel, grosor)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
    pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pintor.setPen(pluma)
    pintor.drawPath(trazo)
    pintor.restore()


#: Colores de marca del icono de la aplicación: los del logo en el tema
#: oscuro. Fijos a propósito, para que el icono del ejecutable y de la barra
#: de tareas no cambie según el tema que se use dentro de la app.
_MARCA_CLARO = "#7FC0FF"
_MARCA_MEDIO = "#2A8EFF"
_MARCA_HONDO = "#1E6FE0"


def icono_app(lado: int = 256) -> QPixmap:
    """
    El icono de la aplicación (ejecutable, barra de tareas, Alt+Tab): la C
    azul del logo, sobre fondo transparente, igual que dentro de la app.
    """
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    degradado = QLinearGradient(0, lado, lado, 0)
    degradado.setColorAt(0.0, QColor(_MARCA_CLARO))
    degradado.setColorAt(0.55, QColor(_MARCA_MEDIO))
    degradado.setColorAt(1.0, QColor(_MARCA_HONDO))
    # Margen mínimo: en un icono cada píxel cuenta, sobre todo a 16 px.
    _pintar_logo(pintor, lado, QBrush(degradado), margen_rel=0.02)
    pintor.end()
    return mapa


def icono_ventana() -> QIcon:
    """El icono de la app en varios tamaños, para ventanas y barra de tareas."""
    icono = QIcon()
    for lado in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icono.addPixmap(icono_app(lado))
    return icono


class Logo(QWidget):
    """El logo como control, para colocarlo en la cabecera."""

    def __init__(self, lado: int = 32, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mapa = logo(lado * 3)          # se dibuja grande y se reduce,
        self.setFixedSize(lado, lado)        # que es lo que lo deja nítido

    def paintEvent(self, evento) -> None:
        pintor = QPainter(self)
        pintor.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        pintor.drawPixmap(self.rect(), self._mapa)
        pintor.end()


# ---------------------------------------------------------------------------
# Iconos de archivo
# ---------------------------------------------------------------------------

def icono_carpeta(lado: int = 64, color: str | None = None) -> QIcon:
    """
    Carpeta de trazo fino, sin el amarillo del sistema.

    Dos cuerpos: una pestaña trasera apenas insinuada y el frente redondeado.
    La profundidad se sugiere con un relleno muy tenue, no con sombras.
    """
    tinta = QColor(color or estilo.AZUL)
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)

    grosor = lado * 0.055
    pluma = QPen(tinta, grosor)
    pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)

    relleno = QColor(tinta)
    relleno.setAlphaF(0.12)

    # Pestaña
    pestana = QPainterPath()
    pestana.moveTo(lado * 0.14, lado * 0.30)
    pestana.lineTo(lado * 0.14, lado * 0.24)
    pestana.lineTo(lado * 0.40, lado * 0.24)
    pestana.lineTo(lado * 0.47, lado * 0.33)
    pintor.setPen(pluma)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawPath(pestana)

    # Cuerpo
    cuerpo = QRectF(lado * 0.12, lado * 0.32, lado * 0.76, lado * 0.46)
    pintor.setBrush(QBrush(relleno))
    pintor.drawRoundedRect(cuerpo, lado * 0.08, lado * 0.08)

    pintor.end()
    return _icono(mapa)


def icono_archivo(lado: int = 64, color: str | None = None) -> QIcon:
    """Hoja con la esquina doblada, en trazo fino."""
    tinta = QColor(color or estilo.TINTA_MEDIA)
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)

    grosor = lado * 0.055
    pluma = QPen(tinta, grosor)
    pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)

    relleno = QColor(tinta)
    relleno.setAlphaF(0.08)

    hoja = QPainterPath()
    hoja.moveTo(lado * 0.24, lado * 0.16)
    hoja.lineTo(lado * 0.58, lado * 0.16)
    hoja.lineTo(lado * 0.78, lado * 0.36)
    hoja.lineTo(lado * 0.78, lado * 0.84)
    hoja.lineTo(lado * 0.24, lado * 0.84)
    hoja.closeSubpath()

    pintor.setPen(pluma)
    pintor.setBrush(QBrush(relleno))
    pintor.drawPath(hoja)

    # El doblez de la esquina
    doblez = QPainterPath()
    doblez.moveTo(lado * 0.58, lado * 0.16)
    doblez.lineTo(lado * 0.58, lado * 0.36)
    doblez.lineTo(lado * 0.78, lado * 0.36)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawPath(doblez)

    pintor.end()
    return _icono(mapa)


def icono_archivo_cifrado(lado: int = 64) -> QIcon:
    """
    Igual que el anterior, con un candado.

    Que el cifrado se vea en el listado y no solo en una columna de texto es
    deliberado: es una de las garantías que el programa ofrece, y conviene que
    se perciba sin leer.
    """
    tinta = QColor(estilo.AZUL)
    base = icono_archivo(lado, estilo.TINTA_MEDIA)

    mapa = base.pixmap(lado, lado)
    pintor = _pintor(mapa)

    pluma = QPen(tinta, lado * 0.055)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
    pintor.setPen(pluma)
    # El cuerpo del candado se rellena con el fondo, no con blanco: sobre el
    # tema oscuro un candado blanco sería una mancha; relleno oscuro deja ver
    # el contorno azul grabado sobre el icono.
    pintor.setBrush(QBrush(QColor(estilo.FONDO)))

    cuerpo = QRectF(lado * 0.50, lado * 0.60, lado * 0.30, lado * 0.24)
    pintor.drawRoundedRect(cuerpo, lado * 0.05, lado * 0.05)

    arco = QRectF(lado * 0.57, lado * 0.47, lado * 0.16, lado * 0.22)
    pintor.setBrush(Qt.BrushStyle.NoBrush)
    pintor.drawArc(arco, 0, 180 * 16)

    pintor.end()
    return _icono(mapa)


# ---------------------------------------------------------------------------
# Iconos de la barra de herramientas
#
# Trazo fino, estilo lineal (FontAwesome / Material), para una barra de iconos
# con tooltips. Se dibujan por código por la misma razón que el resto: el
# ejecutable viaja sin recursos externos y recolorar es editar `estilo.py`.
# ---------------------------------------------------------------------------

def _ruta(lado: float, puntos, cerrar: bool = False) -> QPainterPath:
    """Construye un trazo a partir de puntos en fracción del lado."""
    r = QPainterPath(QPointF(puntos[0][0] * lado, puntos[0][1] * lado))
    for x, y in puntos[1:]:
        r.lineTo(x * lado, y * lado)
    if cerrar:
        r.closeSubpath()
    return r


def icono_nueva_carpeta(lado: int = 64, color: str | None = None) -> QIcon:
    """Carpeta con un «+»: crear una carpeta nueva."""
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    _pluma(pintor, QColor(color or estilo.TINTA_MEDIA), lado * 0.072)
    pintor.drawPath(_ruta(lado, [
        (0.14, 0.32), (0.14, 0.26), (0.40, 0.26), (0.47, 0.34)]))
    pintor.drawPath(_ruta(lado, [
        (0.14, 0.34), (0.14, 0.76), (0.86, 0.76), (0.86, 0.40), (0.47, 0.40)]))
    # El signo «+»
    pintor.drawPath(_ruta(lado, [(0.62, 0.50), (0.62, 0.66)]))
    pintor.drawPath(_ruta(lado, [(0.54, 0.58), (0.70, 0.58)]))
    pintor.end()
    return _icono(mapa)


def icono_anadir(lado: int = 64, color: str | None = None) -> QIcon:
    """Bandeja con flecha hacia arriba: añadir (subir) un archivo al almacén."""
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    _pluma(pintor, QColor(color or estilo.TINTA_MEDIA), lado * 0.072)
    pintor.drawPath(_ruta(lado, [
        (0.22, 0.60), (0.22, 0.80), (0.78, 0.80), (0.78, 0.60)]))
    pintor.drawPath(_ruta(lado, [(0.50, 0.66), (0.50, 0.22)]))
    pintor.drawPath(_ruta(lado, [(0.37, 0.35), (0.50, 0.22), (0.63, 0.35)]))
    pintor.end()
    return _icono(mapa)


def icono_guardar(lado: int = 64, color: str | None = None) -> QIcon:
    """Bandeja con flecha hacia abajo: guardar una copia en el disco."""
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    _pluma(pintor, QColor(color or estilo.TINTA_MEDIA), lado * 0.072)
    pintor.drawPath(_ruta(lado, [
        (0.22, 0.60), (0.22, 0.80), (0.78, 0.80), (0.78, 0.60)]))
    pintor.drawPath(_ruta(lado, [(0.50, 0.20), (0.50, 0.64)]))
    pintor.drawPath(_ruta(lado, [(0.37, 0.51), (0.50, 0.64), (0.63, 0.51)]))
    pintor.end()
    return _icono(mapa)


def icono_renombrar(lado: int = 64, color: str | None = None) -> QIcon:
    """Lápiz: renombrar."""
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    _pluma(pintor, QColor(color or estilo.TINTA_MEDIA), lado * 0.072)
    # Cuerpo del lápiz (paralelogramo) en la anti-diagonal.
    pintor.drawPath(_ruta(lado, [
        (0.30, 0.72), (0.62, 0.30), (0.74, 0.39), (0.42, 0.81)], cerrar=True))
    # Banda que separa la punta.
    pintor.drawPath(_ruta(lado, [(0.36, 0.63), (0.50, 0.72)]))
    pintor.end()
    return _icono(mapa)


def icono_eliminar(lado: int = 64, color: str | None = None) -> QIcon:
    """Papelera: eliminar."""
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    _pluma(pintor, QColor(color or estilo.TINTA_MEDIA), lado * 0.072)
    pintor.drawPath(_ruta(lado, [(0.20, 0.30), (0.80, 0.30)]))      # tapa
    pintor.drawPath(_ruta(lado, [
        (0.42, 0.30), (0.42, 0.23), (0.58, 0.23), (0.58, 0.30)]))   # asa
    pintor.drawPath(_ruta(lado, [
        (0.28, 0.34), (0.33, 0.80), (0.67, 0.80), (0.72, 0.34)]))   # cubo
    pintor.drawPath(_ruta(lado, [(0.44, 0.44), (0.44, 0.70)]))      # ranura
    pintor.drawPath(_ruta(lado, [(0.56, 0.44), (0.56, 0.70)]))      # ranura
    pintor.end()
    return _icono(mapa)


def _iniciales(texto: str) -> str:
    partes = [p for p in texto.replace(".", " ").split() if p]
    if len(partes) >= 2:
        return (partes[0][:1] + partes[1][:1]).upper()
    return (texto[:2] or "?").upper()


def avatar(texto: str, lado: int = 56) -> QIcon:
    """Círculo sólido del acento con las iniciales en blanco (estilo panel)."""
    iniciales = _iniciales(texto)
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QBrush(QColor(estilo.ACENTO)))
    pintor.drawEllipse(QRectF(0, 0, lado, lado))

    pintor.setPen(QColor(estilo.BLANCO))
    fuente = pintor.font()
    fuente.setPixelSize(int(lado * (0.40 if len(iniciales) > 1 else 0.46)))
    fuente.setWeight(QFont.Weight.DemiBold)
    pintor.setFont(fuente)
    pintor.drawText(mapa.rect(), Qt.AlignmentFlag.AlignCenter, iniciales)
    pintor.end()
    return _icono(mapa)


def logo_insignia(lado: int = 40) -> QPixmap:
    """El logo dentro de un cuadrado redondeado del acento (marca del panel)."""
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QBrush(QColor(estilo.ACENTO)))
    r = lado * 0.28
    pintor.drawRoundedRect(QRectF(0, 0, lado, lado), r, r)

    interior = lado * 0.6
    trazo = _trazo_hexagono_abierto(interior)
    grosor = interior * 0.17
    tinta = trazo.boundingRect().adjusted(-grosor / 2, -grosor / 2,
                                          grosor / 2, grosor / 2)
    pintor.translate(lado / 2, lado / 2)
    escala = (lado * 0.52) / max(tinta.width(), tinta.height())
    pintor.scale(escala, escala)
    pintor.translate(-tinta.center().x(), -tinta.center().y())
    pluma = QPen(QColor(estilo.BLANCO), grosor)
    pluma.setCapStyle(Qt.PenCapStyle.RoundCap)
    pluma.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pintor.setPen(pluma)
    pintor.drawPath(trazo)
    pintor.end()
    return mapa


def icono_tema(mostrar_sol: bool, lado: int = 48,
               color: str | None = None) -> QIcon:
    """Sol (para ir a claro) o luna (para ir a oscuro)."""
    tinta = QColor(color or estilo.TINTA_MEDIA)
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    if mostrar_sol:
        _pluma(pintor, tinta, lado * 0.06)
        import math
        c = lado / 2
        pintor.drawEllipse(QRectF(lado * 0.34, lado * 0.34, lado * 0.32, lado * 0.32))
        for i in range(8):
            a = math.radians(45 * i)
            x1 = c + math.cos(a) * lado * 0.26; y1 = c + math.sin(a) * lado * 0.26
            x2 = c + math.cos(a) * lado * 0.36; y2 = c + math.sin(a) * lado * 0.36
            pintor.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    else:
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QBrush(tinta))
        grande = QPainterPath()
        grande.addEllipse(QRectF(lado * 0.26, lado * 0.22, lado * 0.52, lado * 0.52))
        pequeno = QPainterPath()
        pequeno.addEllipse(QRectF(lado * 0.42, lado * 0.14, lado * 0.52, lado * 0.52))
        pintor.drawPath(grande.subtracted(pequeno))
    pintor.end()
    return _icono(mapa)


def icono_salir(lado: int = 48, color: str | None = None) -> QIcon:
    """Flecha saliendo de un marco: cerrar sesión."""
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    _pluma(pintor, QColor(color or estilo.TINTA_MEDIA), lado * 0.07)
    pintor.drawPath(_ruta(lado, [
        (0.44, 0.24), (0.24, 0.24), (0.24, 0.76), (0.44, 0.76)]))
    pintor.drawPath(_ruta(lado, [(0.44, 0.50), (0.74, 0.50)]))
    pintor.drawPath(_ruta(lado, [(0.62, 0.38), (0.76, 0.50), (0.62, 0.62)]))
    pintor.end()
    return _icono(mapa)


def icono_permiso(concedido: bool, lado: int = 40) -> QIcon:
    """
    Marca pequeña para la lista de permisos del panel derecho.

    Concedido: un visto en azul (la marca significa «activo»). Denegado: un
    aspa en rojo. El icono lleva el color; el texto de la fila queda sobrio.
    """
    mapa = _lienzo(lado)
    pintor = _pintor(mapa)
    if concedido:
        _pluma(pintor, QColor(estilo.AZUL), lado * 0.11)
        pintor.drawPath(_ruta(lado, [(0.24, 0.52), (0.42, 0.70), (0.76, 0.32)]))
    else:
        _pluma(pintor, QColor(estilo.NEGADO), lado * 0.10)
        pintor.drawPath(_ruta(lado, [(0.32, 0.32), (0.68, 0.68)]))
        pintor.drawPath(_ruta(lado, [(0.68, 0.32), (0.32, 0.68)]))
    pintor.end()
    return _icono(mapa)


# ---------------------------------------------------------------------------
# Iconos de los avisos (diálogos propios)
# ---------------------------------------------------------------------------

_COLOR_AVISO = {
    "info": None,          # se rellena con el acento del tema
    "exito": None,
    "advertencia": "#E0A82E",
    "error": None,
    "pregunta": None,
}


def icono_aviso(tipo: str, lado: int = 44) -> QIcon:
    """
    Insignia circular para los diálogos: un disco teñido con el color del tipo
    y un glifo encima (i, ✓, !, ✕, ?). Da a cada aviso una lectura inmediata.
    """
    base = {
        "info": estilo.ACENTO, "exito": estilo.VERDE, "advertencia": "#E0A82E",
        "error": estilo.NEGADO, "pregunta": estilo.ACENTO,
    }.get(tipo, estilo.ACENTO)
    color = QColor(base)

    mapa = _lienzo(lado)
    pintor = _pintor(mapa)

    fondo = QColor(color)
    fondo.setAlphaF(0.16)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QBrush(fondo))
    pintor.drawEllipse(QRectF(0, 0, lado, lado))

    if tipo in ("info", "pregunta"):
        pintor.setPen(color)
        fuente = pintor.font()
        fuente.setPixelSize(int(lado * 0.52))
        fuente.setWeight(QFont.Weight.Bold)
        pintor.setFont(fuente)
        pintor.drawText(mapa.rect(), Qt.AlignmentFlag.AlignCenter,
                        "i" if tipo == "info" else "?")
    elif tipo == "exito":
        _pluma(pintor, color, lado * 0.09)
        pintor.drawPath(_ruta(lado, [(0.30, 0.52), (0.44, 0.66), (0.70, 0.36)]))
    elif tipo == "advertencia":
        _pluma(pintor, color, lado * 0.09)
        pintor.drawPath(_ruta(lado, [(0.50, 0.28), (0.50, 0.56)]))
        pintor.setPen(Qt.PenStyle.NoPen)
        pintor.setBrush(QBrush(color))
        pintor.drawEllipse(QRectF(lado * 0.455, lado * 0.64, lado * 0.09, lado * 0.09))
    else:  # error
        _pluma(pintor, color, lado * 0.09)
        pintor.drawPath(_ruta(lado, [(0.36, 0.36), (0.64, 0.64)]))
        pintor.drawPath(_ruta(lado, [(0.64, 0.36), (0.36, 0.64)]))

    pintor.end()
    return _icono(mapa)


def icono_estado(tipo: str, lado: int = 56) -> QIcon:
    """
    Icono grande y sobrio para los estados vacíos de la vista (carpeta vacía,
    carpeta protegida, error). Un disco muy tenue de fondo y, encima, un glifo
    dibujado a trazo en un tono apagado: comunica la situación sin gritar.
    """
    acento = tipo in ("candado", "error")
    tinte = estilo.NEGADO if tipo == "error" else estilo.ACENTO
    glifo = QColor(estilo.ACENTO if acento else estilo.TINTA_TENUE)
    if tipo == "error":
        glifo = QColor(estilo.NEGADO)

    mapa = _lienzo(lado)
    pintor = _pintor(mapa)

    fondo = QColor(tinte if acento else estilo.TINTA_TENUE)
    fondo.setAlphaF(0.12 if acento else 0.10)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QBrush(fondo))
    pintor.drawEllipse(QRectF(0, 0, lado, lado))

    grosor = lado * 0.055
    if tipo == "carpeta":
        # Carpeta abierta, trazo limpio.
        _pluma(pintor, glifo, grosor)
        cuerpo = _ruta(lado, [
            (0.26, 0.38), (0.26, 0.68), (0.74, 0.68), (0.74, 0.44),
            (0.50, 0.44), (0.44, 0.38), (0.26, 0.38),
        ], cerrar=True)
        pintor.drawPath(cuerpo)
    elif tipo == "candado":
        # Candado: arco + cuerpo.
        _pluma(pintor, glifo, grosor)
        arco = QPainterPath()
        arco.moveTo(lado * 0.40, lado * 0.46)
        arco.lineTo(lado * 0.40, lado * 0.40)
        arco.arcTo(QRectF(lado * 0.40, lado * 0.30, lado * 0.20, lado * 0.20),
                   180, -180)
        arco.lineTo(lado * 0.60, lado * 0.46)
        pintor.drawPath(arco)
        pintor.setPen(Qt.PenStyle.NoPen)
        cuerpo = QColor(glifo)
        cuerpo.setAlphaF(0.90)
        pintor.setBrush(QBrush(cuerpo))
        radio = lado * 0.035
        pintor.drawRoundedRect(QRectF(lado * 0.34, lado * 0.46,
                                      lado * 0.32, lado * 0.24), radio, radio)
    else:  # error u otro
        _pluma(pintor, glifo, grosor)
        pintor.drawPath(_ruta(lado, [(0.38, 0.38), (0.62, 0.62)]))
        pintor.drawPath(_ruta(lado, [(0.62, 0.38), (0.38, 0.62)]))

    pintor.end()
    return _icono(mapa)
