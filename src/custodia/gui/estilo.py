# -*- coding: utf-8 -*-
"""
Lenguaje visual de Custodia — estilo «dashboard» con tema oscuro y claro.

Inspirado en un panel moderno: barra lateral con la marca arriba y el perfil
abajo, una barra superior con interruptor de tema, superficies sobrias y el
color reservado para la acción y el estado. Dos temas completos —oscuro casi
negro y claro— que se intercambian en caliente.

------------------------------------------------------------------------------
Cómo funciona el cambio de tema
------------------------------------------------------------------------------
`TEMAS` guarda los dos diccionarios de color. `aplicar(nombre)` fija el tema
actual: actualiza las constantes de módulo (que leen los iconos) y deja listo
`HOJA`, el QSS que la ventana aplica con `app.setStyleSheet(estilo.HOJA)`.
Para alternar, la ventana llama a `aplicar("claro" | "oscuro")`, vuelve a pedir
`estilo.HOJA`, reconstruye los iconos (su color depende del tema) y refresca.
"""

# ============================================================================
#  PALETAS  —  valores tomados de la referencia, uno por tema
# ============================================================================

TEMAS = {
    "oscuro": {
        "FONDO": "#0B0B0D", "SIDEBAR": "#08080A", "PANEL": "#151518",
        "ELEVADO": "#1E1E22", "CAMPO": "#232327",
        "BORDE": "#26262B", "BORDE_SUAVE": "#1B1B1F",
        "TINTA": "#F2F4F7", "TINTA_MEDIA": "#9BA0A6", "TINTA_TENUE": "#6B7075",
        "ACENTO": "#2A8EFF", "ACENTO_HONDO": "#1E6FE0", "ACENTO_CLARO": "#7FC0FF",
        "ACENTO_VELO": "rgba(42,142,255,0.16)", "SELECCION": "#17293F",
        "NEGADO": "#F2655C", "NEGADO_VELO": "rgba(242,101,92,0.15)",
        "VERDE": "#34D399", "VERDE_VELO": "rgba(52,211,153,0.15)",
    },
    "claro": {
        "FONDO": "#F9FAFB", "SIDEBAR": "#FFFFFF", "PANEL": "#FFFFFF",
        "ELEVADO": "#EEF2F4", "CAMPO": "#FFFFFF",
        "BORDE": "#E3E7EB", "BORDE_SUAVE": "#EDF0F2",
        "TINTA": "#0F1720", "TINTA_MEDIA": "#5E6568", "TINTA_TENUE": "#8B9096",
        "ACENTO": "#1C7DE6", "ACENTO_HONDO": "#0F62C0", "ACENTO_CLARO": "#7FC0FF",
        "ACENTO_VELO": "#E8F1FD", "SELECCION": "#E8F1FD",
        "NEGADO": "#DC2626", "NEGADO_VELO": "#FDECEC",
        "VERDE": "#16A34A", "VERDE_VELO": "#E7F6EC",
    },
}

BLANCO = "#FFFFFF"
RADIO = 12
RADIO_PEQUENO = 8

# Nombre del tema por defecto (la referencia es oscura).
TEMA_ACTUAL = "oscuro"

# -- constantes de módulo que leen los iconos (se rellenan en `aplicar`) ------
FONDO = SIDEBAR = PANEL = ELEVADO = CAMPO = BORDE = BORDE_SUAVE = ""
TINTA = TINTA_MEDIA = TINTA_TENUE = ""
ACENTO = ACENTO_HONDO = ACENTO_CLARO = ACENTO_VELO = SELECCION = ""
NEGADO = NEGADO_VELO = VERDE = VERDE_VELO = ""
# Alias históricos que usan los iconos (AZUL == ACENTO).
AZUL = AZUL_HONDO = AZUL_CLARO = AZUL_VELO = ""

HOJA = ""


def _hoja(t: dict) -> str:
    """Construye el QSS completo a partir de un diccionario de tema."""
    FONDO = t["FONDO"]; SIDEBAR = t["SIDEBAR"]; PANEL = t["PANEL"]
    ELEVADO = t["ELEVADO"]; CAMPO = t["CAMPO"]
    BORDE = t["BORDE"]; BORDE_SUAVE = t["BORDE_SUAVE"]
    TINTA = t["TINTA"]; TINTA_MEDIA = t["TINTA_MEDIA"]; TINTA_TENUE = t["TINTA_TENUE"]
    ACENTO = t["ACENTO"]; ACENTO_HONDO = t["ACENTO_HONDO"]
    ACENTO_VELO = t["ACENTO_VELO"]; SELECCION = t["SELECCION"]
    NEGADO = t["NEGADO"]; NEGADO_VELO = t["NEGADO_VELO"]
    VERDE = t["VERDE"]; VERDE_VELO = t["VERDE_VELO"]
    return f"""
/* ---- base ---------------------------------------------------------------- */
QWidget {{
    font-family: "Inter", "Segoe UI Variable Text", "Segoe UI", sans-serif;
    font-size: 13px;
    color: {TINTA};
}}
QMainWindow, QDialog {{ background: {FONDO}; }}
QToolTip {{
    background: {PANEL}; color: {TINTA};
    border: 1px solid {BORDE}; border-radius: 7px;
    padding: 6px 9px; font-size: 12px;
}}

/* ---- barra lateral ------------------------------------------------------- */
QWidget#barraLateral {{
    background: {SIDEBAR};
    border-right: 1px solid {BORDE};
}}
QLabel#marca {{ color: {TINTA}; font-size: 15px; font-weight: 700; }}
QLabel#marcaSub {{ color: {TINTA_TENUE}; font-size: 10px; font-weight: 600; letter-spacing: 1.2px; }}
QLabel#seccion {{ color: {TINTA_TENUE}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}

/* navegación / árbol de carpetas */
QTreeWidget#lateral {{ background: transparent; border: none; outline: none; }}
QTreeWidget#lateral::item {{
    padding: 9px 10px; border-radius: {RADIO_PEQUENO}px;
    color: {TINTA_MEDIA}; min-height: 20px;
}}
QTreeWidget#lateral::item:hover {{ background: {ELEVADO}; color: {TINTA}; }}
QTreeWidget#lateral::item:selected {{ background: {SELECCION}; color: {ACENTO}; }}
/* Se eliminan las líneas-guía del árbol (los conectores verticales que Windows
   dibuja y que, en la fila seleccionada, salían como barras azules). Se quita
   su imagen; las flechas de expandir/contraer de las carpetas se conservan. */
QTreeWidget#lateral::branch {{ background: transparent; }}
QTreeWidget#lateral::branch:has-siblings:!adjoins-item,
QTreeWidget#lateral::branch:has-siblings:adjoins-item,
QTreeWidget#lateral::branch:!has-children:!has-siblings:adjoins-item {{
    border-image: none;
    image: none;
    background: transparent;
}}

/* tarjeta de usuario (abajo) */
QWidget#chipUsuario {{ background: transparent; border-top: 1px solid {BORDE}; }}
QLabel#chipNombre {{ color: {TINTA}; font-size: 13px; font-weight: 600; }}
QLabel#chipRol {{ color: {TINTA_TENUE}; font-size: 11px; }}
QToolButton#salir {{ background: transparent; border: none; border-radius: 7px; padding: 6px; }}
QToolButton#salir:hover {{ background: {ELEVADO}; }}

/* ---- barra superior ------------------------------------------------------ */
QWidget#cabecera {{ background: {FONDO}; border-bottom: 1px solid {BORDE}; }}
QLabel#migas {{ color: {TINTA_TENUE}; font-size: 13px; }}
QToolButton#toggleTema {{
    background: {PANEL}; border: 1px solid {BORDE};
    border-radius: {RADIO_PEQUENO}px; padding: 7px;
}}
QToolButton#toggleTema:hover {{ border-color: {ACENTO}; }}
QToolButton#perfil {{
    background: {PANEL}; border: 1px solid {BORDE};
    border-radius: {RADIO_PEQUENO}px; padding: 5px 10px 5px 6px;
    color: {TINTA}; font-size: 13px; font-weight: 600;
}}
QToolButton#perfil:hover {{ border-color: {ACENTO}; }}
QToolButton#perfil::menu-indicator {{ subcontrol-position: right center; right: 6px; }}

/* ---- contenido ----------------------------------------------------------- */
QLabel#titulo {{ color: {TINTA}; font-size: 24px; font-weight: 700; }}
QLabel#subtitulo {{ color: {TINTA_MEDIA}; font-size: 13px; }}

/* barra de herramientas de iconos */
QToolButton#herramienta, QToolButton#herramientaPeligro {{
    background: {PANEL}; border: 1px solid {BORDE};
    border-radius: {RADIO_PEQUENO}px; padding: 8px;
}}
QToolButton#herramienta:hover {{ background: {ELEVADO}; border-color: {ACENTO}; }}
QToolButton#herramientaPeligro:hover {{ background: {NEGADO_VELO}; border-color: {NEGADO}; }}

/* ---- tabla de archivos --------------------------------------------------- */
QTreeWidget#listado {{
    background: {PANEL}; border: 1px solid {BORDE};
    border-radius: {RADIO}px; outline: none;
    gridline-color: transparent;
}}
QTreeWidget#listado::item {{
    padding: 0px 8px; border: none;
    border-bottom: 1px solid {BORDE_SUAVE}; color: {TINTA};
}}
QTreeWidget#listado::item:hover {{ background: {ELEVADO}; }}
QTreeWidget#listado::item:selected {{ background: {SELECCION}; color: {TINTA}; }}
QHeaderView::section {{
    background: {PANEL}; color: {TINTA_TENUE};
    border: none; border-bottom: 1px solid {BORDE};
    padding: 12px 8px; font-size: 12px; font-weight: 600;
}}
QHeaderView::section:first {{ border-top-left-radius: {RADIO}px; }}
QHeaderView::section:last {{ border-top-right-radius: {RADIO}px; }}

/* ---- tarjeta de permisos ------------------------------------------------- */
QWidget#tarjeta {{ background: {PANEL}; border: 1px solid {BORDE}; border-radius: {RADIO}px; }}
QFrame#divisorPanel {{ background: {BORDE}; border: none; }}
QLabel#rotulo {{ color: {TINTA_TENUE}; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; }}
QLabel#elemento {{ color: {TINTA}; font-size: 16px; font-weight: 600; }}
QLabel#propietario {{ color: {TINTA_MEDIA}; font-size: 13px; }}

/* ---- estado vacío de la vista principal ---------------------------------- */
QWidget#estadoVacio {{
    background: {PANEL}; border: 1px solid {BORDE}; border-radius: {RADIO}px;
}}
QLabel#vacioTitulo {{ color: {TINTA}; font-size: 17px; font-weight: 600; }}
QLabel#vacioTexto {{ color: {TINTA_MEDIA}; font-size: 13px; }}
QLabel#nota {{ color: {TINTA_TENUE}; font-size: 11px; }}
QLabel#permiso {{ color: {TINTA_TENUE}; background: transparent; padding: 6px 2px; font-size: 13px; }}
QLabel#permiso[concedido="true"] {{ color: {TINTA}; }}

/* píldora de estado (p. ej. «Cifrado») */
QLabel#pildora {{
    color: {ACENTO}; background: {ACENTO_VELO};
    border-radius: 999px; padding: 3px 11px; font-size: 11px; font-weight: 600;
}}

/* ---- bitácora de auditoría ---------------------------------------------- */
QLabel#pildoraOk {{
    color: {VERDE}; background: {VERDE_VELO};
    border-radius: 999px; padding: 3px 12px; font-size: 11px; font-weight: 600;
}}
QLabel#pildoraNo {{
    color: {NEGADO}; background: {NEGADO_VELO};
    border-radius: 999px; padding: 3px 12px; font-size: 11px; font-weight: 600;
}}
QLabel#filtroRotulo {{
    color: {TINTA_TENUE}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}}
QLabel#contador {{ color: {TINTA_TENUE}; font-size: 12px; }}
QWidget#detallePanel {{
    background: {PANEL}; border: 1px solid {BORDE}; border-radius: {RADIO}px;
}}
QLabel#detalleVacio {{ color: {TINTA_TENUE}; font-size: 13px; }}
QLabel#detalleTitulo {{ color: {TINTA}; font-size: 16px; font-weight: 600; }}
QLabel#detalleCampo {{ color: {TINTA_TENUE}; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }}
QLabel#detalleValor {{ color: {TINTA}; font-size: 13px; }}
QLabel#detalleMono {{
    color: {TINTA}; font-size: 12px;
    font-family: "Cascadia Code", "Consolas", "Menlo", monospace;
}}
QLineEdit#buscador {{ padding-left: 11px; }}

/* ---- formularios --------------------------------------------------------- */
QLineEdit, QComboBox {{
    background: {CAMPO}; border: 1px solid {BORDE};
    border-radius: {RADIO_PEQUENO}px; padding: 9px 11px; color: {TINTA};
    selection-background-color: {ACENTO}; selection-color: {BLANCO};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACENTO}; }}
QComboBox QAbstractItemView {{
    background: {PANEL}; border: 1px solid {BORDE};
    border-radius: {RADIO_PEQUENO}px; selection-background-color: {ACENTO_VELO};
    selection-color: {TINTA}; outline: none;
}}
QGroupBox {{
    border: 1px solid {BORDE}; border-radius: {RADIO}px;
    margin-top: 14px; padding: 16px 14px 14px 14px; background: {PANEL};
}}
QGroupBox::title {{
    subcontrol-origin: margin; left: 14px; padding: 0 6px;
    color: {TINTA_TENUE}; font-size: 11px; font-weight: 700; letter-spacing: 0.6px;
}}
QPushButton {{
    background: {PANEL}; border: 1px solid {BORDE};
    border-radius: {RADIO_PEQUENO}px; padding: 9px 15px; color: {TINTA};
}}
QPushButton:hover {{ background: {ELEVADO}; border-color: {ACENTO}; }}
QPushButton#principal {{ background: {ACENTO}; border: 1px solid {ACENTO}; color: {BLANCO}; font-weight: 600; }}
QPushButton#principal:hover {{ background: {ACENTO_HONDO}; border-color: {ACENTO_HONDO}; }}
QPushButton#principalPeligro {{ background: {NEGADO}; border: 1px solid {NEGADO}; color: {BLANCO}; font-weight: 600; }}
QPushButton#principalPeligro:hover {{ background: #B3453C; border-color: #B3453C; }}
QCheckBox {{ spacing: 8px; }}

/* ---- diálogos propios (avisos) ------------------------------------------ */
QDialog#avisoModal {{ background: {PANEL}; }}
QLabel#avisoTitulo {{ color: {TINTA}; font-size: 16px; font-weight: 600; }}
QLabel#avisoMensaje {{ color: {TINTA_MEDIA}; font-size: 13px; }}

/* ---- menús --------------------------------------------------------------- */
QMenu {{ background: {PANEL}; border: 1px solid {BORDE}; border-radius: {RADIO_PEQUENO}px; padding: 7px; }}
QMenu::item {{ padding: 9px 26px 9px 14px; border-radius: 6px; color: {TINTA}; }}
QMenu::item:selected {{ background: {ACENTO_VELO}; color: {ACENTO}; }}
QMenu::separator {{ height: 1px; background: {BORDE}; margin: 6px 8px; }}

/* ---- scrollbars ---------------------------------------------------------- */
QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDE}; border-radius: 5px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {TINTA_TENUE}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}

/* ---- ingreso ------------------------------------------------------------- */
QDialog#ingreso {{ background: {PANEL}; }}
QLabel#tituloIngreso {{ font-size: 27px; font-weight: 700; color: {TINTA}; }}
QLabel#subtituloIngreso {{ color: {TINTA_MEDIA}; font-size: 13px; }}
QLabel#aviso {{
    color: {NEGADO}; background: {NEGADO_VELO};
    border-radius: {RADIO_PEQUENO}px; padding: 10px 12px; font-size: 12px;
}}
"""


def aplicar(nombre: str) -> str:
    """Fija el tema actual, actualiza las constantes y devuelve el QSS."""
    global TEMA_ACTUAL, HOJA
    global FONDO, SIDEBAR, PANEL, ELEVADO, CAMPO, BORDE, BORDE_SUAVE
    global TINTA, TINTA_MEDIA, TINTA_TENUE
    global ACENTO, ACENTO_HONDO, ACENTO_CLARO, ACENTO_VELO, SELECCION
    global NEGADO, NEGADO_VELO, VERDE, VERDE_VELO
    global AZUL, AZUL_HONDO, AZUL_CLARO, AZUL_VELO

    t = TEMAS[nombre]
    TEMA_ACTUAL = nombre
    FONDO = t["FONDO"]; SIDEBAR = t["SIDEBAR"]; PANEL = t["PANEL"]
    ELEVADO = t["ELEVADO"]; CAMPO = t["CAMPO"]
    BORDE = t["BORDE"]; BORDE_SUAVE = t["BORDE_SUAVE"]
    TINTA = t["TINTA"]; TINTA_MEDIA = t["TINTA_MEDIA"]; TINTA_TENUE = t["TINTA_TENUE"]
    ACENTO = t["ACENTO"]; ACENTO_HONDO = t["ACENTO_HONDO"]; ACENTO_CLARO = t["ACENTO_CLARO"]
    ACENTO_VELO = t["ACENTO_VELO"]; SELECCION = t["SELECCION"]
    NEGADO = t["NEGADO"]; NEGADO_VELO = t["NEGADO_VELO"]
    VERDE = t["VERDE"]; VERDE_VELO = t["VERDE_VELO"]
    # Alias para los iconos (dibujan con AZUL == ACENTO).
    AZUL = ACENTO; AZUL_HONDO = ACENTO_HONDO; AZUL_CLARO = ACENTO_CLARO
    AZUL_VELO = ACENTO_VELO
    HOJA = _hoja(t)
    return HOJA


def alternar() -> str:
    """Cambia al otro tema y devuelve el QSS nuevo."""
    return aplicar("claro" if TEMA_ACTUAL == "oscuro" else "oscuro")


def paleta():
    """
    QPalette acorde al tema actual.

    Imprescindible: la hoja de estilo solo pinta los controles con regla
    propia; los contenedores sin fondo heredan el color «Window» de la paleta.
    Si esa paleta es clara (la de Windows por defecto), el modo oscuro deja
    zonas blancas entre los paneles. Fijar aquí Window = FONDO lo evita.
    """
    from PySide6.QtGui import QColor, QPalette
    C = QColor
    R = QPalette.ColorRole
    p = QPalette()
    p.setColor(R.Window, C(FONDO))
    p.setColor(R.WindowText, C(TINTA))
    p.setColor(R.Base, C(PANEL))
    p.setColor(R.AlternateBase, C(ELEVADO))
    p.setColor(R.Text, C(TINTA))
    p.setColor(R.Button, C(PANEL))
    p.setColor(R.ButtonText, C(TINTA))
    p.setColor(R.ToolTipBase, C(PANEL))
    p.setColor(R.ToolTipText, C(TINTA))
    p.setColor(R.Highlight, C(SELECCION))
    p.setColor(R.HighlightedText, C(TINTA))
    p.setColor(R.PlaceholderText, C(TINTA_TENUE))
    p.setColor(R.BrightText, C(NEGADO))
    return p


def tenir_barra_titulo(widget, oscuro: bool | None = None) -> None:
    """
    Tiñe la barra de título NATIVA de una ventana según el tema (solo Windows).

    La hoja de estilo y la paleta pintan el interior de la ventana, pero la
    barra de título la dibuja el sistema operativo. En modo oscuro quedaba, por
    eso, una franja blanca arriba de cada ventana. Esto se lo pide a Windows con
    `DwmSetWindowAttribute` (modo oscuro inmersivo). Es inofensivo en otros
    sistemas: si la llamada no existe, se ignora.
    """
    if oscuro is None:
        oscuro = TEMA_ACTUAL == "oscuro"
    try:
        import ctypes

        hwnd = int(widget.winId())
        valor = ctypes.c_int(1 if oscuro else 0)
        dwm = ctypes.windll.dwmapi
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win10 2004+); 19 en compilaciones
        # anteriores. Se intentan ambos; el que no aplique devuelve un error que
        # se descarta.
        for atributo in (20, 19):
            dwm.DwmSetWindowAttribute(hwnd, atributo, ctypes.byref(valor),
                                      ctypes.sizeof(valor))
        # Forzar que el marco se repinte de inmediato (NOMOVE|NOSIZE|NOZORDER|
        # FRAMECHANGED), para que el cambio se vea sin mover la ventana.
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                          0x0002 | 0x0001 | 0x0004 | 0x0020)
    except Exception:
        pass


# Tema inicial.
aplicar(TEMA_ACTUAL)
