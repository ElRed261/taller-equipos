"""Iconos de la aplicación, dibujados como SVG propios.

Nada se descarga ni se referencia por URL: los SVG viven dentro del paquete, así
la aplicación funciona sin red y el instalador no depende de nada externo.

El cargador **tinta** cada icono con el color pedido. Los SVG traen un color
razonable para editarlos a mano, pero en pantalla manda el color que pide el
código, que es el que respeta el contraste de la paleta: blanco sobre el botón
azul, gris sobre fondo claro, blanco sobre el rojo del rail.

Los resultados se cachean: son decenas de llamadas y cada una renderiza un SVG.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

RUTA_ICONOS: Final = Path(__file__).parent / "assets" / "iconos"

#: Se renderiza al doble y se reduce al pintar, para que no se vea escalonado.
ESCALA: Final = 2


@lru_cache(maxsize=256)
def pixmap_icono(nombre: str, color: str, tamano: int = 18) -> QPixmap:
    """Render one icon at ``tamano`` logical pixels, tinted with ``color``."""
    ruta = RUTA_ICONOS / f"{nombre}.svg"
    lienzo = QPixmap(tamano * ESCALA, tamano * ESCALA)
    lienzo.fill(Qt.GlobalColor.transparent)
    if not ruta.is_file():
        return lienzo

    pintor = QPainter(lienzo)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(str(ruta)).render(pintor)
    # SourceIn pinta solo donde el icono ya dibujó: cambia el color y conserva
    # las transparencias de las esquinas.
    pintor.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    pintor.fillRect(lienzo.rect(), QColor(color))
    pintor.end()
    lienzo.setDevicePixelRatio(ESCALA)
    return lienzo


def icono(nombre: str, color: str, tamano: int = 18) -> QIcon:
    """A QIcon of one of the application icons, tinted."""
    return QIcon(pixmap_icono(nombre, color, tamano))


def existe(nombre: str) -> bool:
    """Whether the icon ships with the application."""
    return (RUTA_ICONOS / f"{nombre}.svg").is_file()
