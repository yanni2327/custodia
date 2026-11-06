# -*- mode: python ; coding: utf-8 -*-
"""
Receta de empaquetado (RNF-07).

Construye un ejecutable único que funciona en un Windows limpio, sin Python
instalado y sin navegador ni servidor local.

    pyinstaller custodia.spec

El resultado queda en dist\\Custodia.exe.

------------------------------------------------------------------------------
Las tres decisiones de este archivo
------------------------------------------------------------------------------
**uac_admin=True.** Incrusta en el ejecutable un manifiesto
`requireAdministrator`, de modo que Windows pide elevación al abrirlo en lugar
de dejar que la aplicación arranque y falle al primer intento de crear una
cuenta. Es obligatorio aquí: administrar cuentas locales y escribir ACL exige
privilegios, y además la clave maestra y la bitácora viven en carpetas donde
solo un proceso elevado puede escribir.

**console=False.** Sin consola detrás de la ventana. El RNF-07 pide un programa
de escritorio, y una ventana negra acompañando a la aplicación delata que
debajo hay un intérprete.

**Exclusiones.** PySide6 trae muchos módulos que este programa no usa, y el
empaquetador los incluiría todos. Quitar el motor web, la parte 3D y QML ahorra
bastante peso (QML sí se incluye: el inicio de sesión ya está hecho en Qt
Quick). Si al construir aparece un `ModuleNotFoundError` en tiempo de
ejecución, el módulo que falte se quita de esta lista.
"""

a = Analysis(
    ["scripts/custodia_gui.py"],
    pathex=["src"],
    binaries=[],
    # La tipografía Inter viaja dentro del ejecutable y se coloca junto al
    # módulo gui, que es donde app.py la busca al arrancar.
    # Las vistas QML (inicio de sesión) viajan igual, en custodia/gui/qml.
    datas=[("src/custodia/gui/recursos/Inter.ttf", "custodia/gui/recursos"),
           ("src/custodia/gui/qml", "custodia/gui/qml")],
    hiddenimports=[
        # pywin32 lo importa de forma indirecta y el empaquetador no lo detecta.
        "win32timezone",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        # QtQuick y QtQml ya NO se excluyen: la interfaz se migra a QML.
        "PySide6.QtQuick3D",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtPdf",
        "PySide6.QtDesigner",
        "tkinter",
        "matplotlib",
        "numpy",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Custodia",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,            # aplicación de escritorio, sin consola
    uac_admin=True,           # manifiesto requireAdministrator
    # Icono del ejecutable: la C de Custodia. Se genera con
    # scripts/generar_icono.py a partir del mismo dibujo del logo de la app.
    icon="src/custodia/gui/recursos/custodia.ico",
    disable_windowed_traceback=False,
)
