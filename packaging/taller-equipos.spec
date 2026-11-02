# -*- mode: python ; coding: utf-8 -*-
"""Empaquetado de la aplicación con PyInstaller.

Un directorio (no un archivo único) por una razón concreta: with `--onefile`
PySide6 se descomprime en un temporal en cada arranque y la ventana tarda varios
segundos en aparecer. En un taller eso se siente como que la aplicación está rota.
El directorio se copia entero y arranca al instante.
"""

import os
from pathlib import Path

RAIZ = Path(SPECPATH).parent
PAQUETE = RAIZ / "src" / "taller"

a = Analysis(
    [str(PAQUETE / "main.py")],
    pathex=[str(RAIZ / "src")],
    binaries=[],
    # El logo y los iconos viajan dentro del paquete: la aplicación no descarga nada.
    datas=[
        (str(PAQUETE / "ui" / "assets"), "taller/ui/assets"),
        # El asistente crea las tablas al instalar: las migraciones viajan adentro.
        (str(RAIZ / "migrations"), "migrations"),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "tkinter", "PIL", "pytest", "mypy", "ruff", "pydoc_data",
        # Qt trae decenas de módulos que esta aplicación no abre. Sin esto el
        # paquete pesa 268 MB y la mitad es WebEngine.
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
        "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
        "PySide6.QtQml", "PySide6.QtQuickControls2",
        "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
        "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
        "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
        "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
        "PySide6.QtPositioning", "PySide6.QtSensors", "PySide6.QtSerialPort",
        "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtRemoteObjects",
        "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtTextToSpeech",
        "PySide6.QtTest", "PySide6.QtSql", "PySide6.QtHelp", "PySide6.QtDesigner",
        "PySide6.QtUiTools", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
        "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvgWidgets",
        "PySide6.QtNetworkAuth", "PySide6.QtHttpServer",
    ],
    noarchive=False,
)

# Los `excludes` de Analysis no sacan los binarios de Qt: el hook de PySide6 copia
# las bibliotecas igual. Se filtran a mano las de módulos que la aplicación no abre.
PROHIBIDOS = (
    "Quick", "Qml", "3D", "WebEngine", "Pdf", "Multimedia", "Charts", "Designer",
    "Bluetooth", "Sensors", "Positioning", "SerialPort", "Scxml", "RemoteObjects",
    "TextToSpeech", "NetworkAuth", "UiTools", "SpatialAudio", "HttpServer",
    "libQt6Test", "libQt6Sql", "libQt6Help", "libQt6OpenGL",
)


def _sin_modulos_inutiles(elementos):
    return [
        elemento
        for elemento in elementos
        if not any(prohibido in Path(elemento[0]).name for prohibido in PROHIBIDOS)
    ]


a.binaries = _sin_modulos_inutiles(a.binaries)
a.datas = _sin_modulos_inutiles(a.datas)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="taller-equipos",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(RAIZ / "packaging" / "icono.ico") if os.name == "nt" else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="taller-equipos",
)
