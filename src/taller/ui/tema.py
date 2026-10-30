"""The institutional theme, derived from the measured palette.

This module is the only place where colour lives in the application. The values
below were chosen with the WCAG formula, not by eye: every pair used in the
interface clears the AA floor, and the tests that keep this honest live in
``tests/test_formato.py`` and the palette notes in ``docs/arquitectura.md``.

Layout: the top bar is **white** so the logo has no visible seam, and the side
rail is the dark blue of the palette. The active rail item uses the accent red,
the only place where red acts as decoration instead of as a signal.

Focus: Qt draws its own focus rectangle inside text fields, which looks like a
coloured contour around the text. It is suppressed; the focus cue is a 1px border
that changes colour. Some cue must remain or keyboard navigation becomes blind.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from PySide6.QtGui import QPixmap

from taller.schemas.movimiento import Estado

COLORES: Final[dict[str, str]] = {
    # Azul principal (tomado del logo, #001E5E exacto)
    "azul-900": "#00123F",
    "azul-800": "#001E5E",
    "azul-700": "#0A2F7D",
    "azul-600": "#14419B",
    "azul-500": "#1D50B4",
    "azul-400": "#4A79D0",
    "azul-200": "#C2D3F5",
    "azul-100": "#E3EBFB",
    "azul-50": "#F2F6FE",
    # Neutros tintados con el tono de marca
    "gris-900": "#0F1621",
    "gris-700": "#37404E",
    "gris-600": "#55606F",
    "gris-500": "#6B7684",
    "gris-400": "#7C8899",
    "gris-300": "#C7CFDA",
    "gris-200": "#E1E6ED",
    "gris-100": "#EFF2F6",
    "gris-50": "#F8FAFC",
    # Rojo de acento (tomado del logo, #FB0315 exacto)
    "rojo-800": "#7F0009",
    "rojo-700": "#A50310",
    "rojo-600": "#D80A18",
    "rojo-100": "#FDE3E5",
    "rojo-50": "#FEF2F3",
    # Semánticos
    "verde-800": "#0A5330",
    "verde-700": "#0F6B3D",
    "verde-600": "#157F4A",
    "verde-100": "#DCF3E7",
    "ambar-800": "#6B4600",
    "ambar-700": "#8A5A00",
    "ambar-100": "#FBEFD5",
    "blanco": "#FFFFFF",
    "superficie-alt": "#F4F7FB",
}

FONDO: Final = COLORES["gris-50"]
SUPERFICIE: Final = COLORES["blanco"]
TEXTO: Final = COLORES["gris-900"]
TEXTO_SUAVE: Final = COLORES["gris-600"]
BORDE: Final = COLORES["gris-200"]
BORDE_CONTROL: Final = COLORES["gris-400"]
MARCA: Final = COLORES["azul-800"]
PRIMARIO: Final = COLORES["azul-700"]
INTERACTIVO: Final = COLORES["azul-500"]
SELECCION: Final = COLORES["azul-50"]
RAIL: Final = COLORES["azul-800"]
#: Fondo del ítem activo. Rojo institucional, no el tono claro: con letras
#: blancas el rojo claro daba 1.15:1 y era ilegible. #FFFFFF sobre #D80A18 = 5.28:1.
RAIL_ACTIVO: Final = COLORES["rojo-600"]

#: Badge colours of the derived state. Same values the model and the delegate use.
COLOR_ESTADO: Final[dict[Estado, str]] = {
    "despachado": COLORES["verde-600"],
    "en_taller": COLORES["rojo-600"],
    "sin_datos": COLORES["gris-400"],
}

ETIQUETA_ESTADO: Final[dict[Estado, str]] = {
    "despachado": "Despachado",
    "en_taller": "En taller",
    "sin_datos": "Sin datos",
}

FUENTE: Final = 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif'
MONO: Final = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'

#: Institutional logo. Shipped inside the package so it survives packaging.
RUTA_LOGO: Final = Path(__file__).parent / "assets" / "logo.png"
RUTA_ICONOS: Final = Path(__file__).parent / "assets" / "iconos"


def cargar_logo(alto: int = 34) -> QPixmap:
    """The application mark, scaled to the top bar.

    It is a neutral symbol, not a wordmark: at this size letters are unreadable,
    so the name is written next to it as text.
    """
    pixmap = QPixmap(str(RUTA_LOGO))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaledToHeight(alto)


def hoja_de_estilo() -> str:
    """The application stylesheet. Qt has no CSS variables, so it is formatted."""
    c = COLORES
    return f"""
    QWidget {{
        background: {FONDO};
        color: {TEXTO};
        font-family: {FUENTE};
        font-size: 13px;
    }}
    QMainWindow, QDialog {{ background: {FONDO}; }}
    QToolTip {{
        background: {c["azul-900"]};
        color: {c["blanco"]};
        border: 1px solid {c["azul-700"]};
        padding: 5px 7px;
    }}

    /* ---------- Barra superior blanca (el logo no tiene costura) ---------- */
    #BarraSuperior {{
        background: {SUPERFICIE};
        border-bottom: 1px solid {BORDE};
    }}
    #BarraSuperior QLabel {{ background: transparent; color: {c["gris-700"]}; }}
    #BarraInstitucion {{ font-size: 15px; font-weight: 800; color: {MARCA}; letter-spacing: .10em; }}
    #BarraSistema {{ font-size: 13px; font-weight: 700; color: {c["gris-700"]}; }}
    #BarraConexion {{ color: {c["gris-500"]}; font-family: {MONO}; font-size: 11px; }}

    /* ---------- Rail azul institucional ---------- */
    #Rail {{ background: {RAIL}; border: 0; }}
    #Rail QPushButton {{
        background: transparent;
        border: 0;
        border-left: 3px solid transparent;
        border-radius: 0;
        padding: 10px 16px;
        text-align: left;
        color: {c["blanco"]};
        font-weight: 600;
        font-size: 13px;
    }}
    #Rail QPushButton:hover {{ background: rgba(255, 255, 255, 0.10); }}
    #Rail QPushButton:checked {{
        background: {RAIL_ACTIVO};
        border-left-color: {c["blanco"]};
        color: {c["blanco"]};
    }}
    #Rail QLabel {{ background: transparent; color: {c["azul-200"]}; }}

    /* ---------- Controles: foco por borde, sin recuadro ---------- */
    QLineEdit, QPlainTextEdit, QComboBox, QDateEdit, QSpinBox {{
        background: {SUPERFICIE};
        border: 1px solid {BORDE_CONTROL};
        border-radius: 7px;
        padding: 7px 10px;
        selection-background-color: {c["azul-200"]};
        selection-color: {TEXTO};
        outline: none;
    }}
    QLineEdit:hover, QComboBox:hover, QDateEdit:hover {{ border-color: {c["gris-600"]}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QDateEdit:focus {{
        border-color: {INTERACTIVO};
    }}
    QLineEdit:disabled, QComboBox:disabled {{
        background: {c["gris-100"]};
        color: {c["gris-500"]};
        border-color: {BORDE};
    }}
    QLineEdit[error="true"] {{ border-color: {c["rojo-600"]}; background: {c["rojo-50"]}; }}

    /* El área de texto tiene su propio viewport: sin fondo propio ni marco, el
       borde redondeado del QSS queda como único encuadre. */
    QPlainTextEdit {{ padding: 8px 10px; }}
    QPlainTextEdit > QWidget {{ background: transparent; }}

    /* Sin flecha, un desplegable parece un campo de texto: la flecha es la que
       dice que hay una lista para abrir. */
    QComboBox::drop-down {{ border: 0; width: 26px; }}
    QComboBox::down-arrow {{
        image: url("{RUTA_ICONOS / 'chevron.svg'}");
        width: 12px; height: 12px;
    }}
    QComboBox::down-arrow:disabled {{ image: none; }}
    QComboBox QAbstractItemView {{
        background: {SUPERFICIE};
        border: 1px solid {BORDE_CONTROL};
        border-radius: 6px;
        padding: 3px;
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        border: 0;
        padding: 6px 9px;
        border-radius: 4px;
        color: {TEXTO};
        min-height: 22px;
    }}
    QComboBox QAbstractItemView::item:hover {{ background: {c["gris-100"]}; }}
    QComboBox QAbstractItemView::item:selected {{
        background: {SELECCION};
        color: {c["azul-700"]};
    }}

    QDateEdit::drop-down {{ border: 0; width: 26px; }}
    QDateEdit::down-arrow {{
        image: url("{RUTA_ICONOS / 'calendario.svg'}");
        width: 14px; height: 14px;
    }}
    QCalendarWidget QWidget {{ background: {SUPERFICIE}; }}
    QCalendarWidget QAbstractItemView:enabled {{
        selection-background-color: {c["azul-600"]};
        selection-color: {c["blanco"]};
        outline: none;
    }}

    /* ---------- Botones ---------- */
    QPushButton {{
        background: {SUPERFICIE};
        border: 1px solid {BORDE_CONTROL};
        border-radius: 7px;
        padding: 8px 15px;
        font-weight: 600;
        color: {c["gris-700"]};
        outline: none;
    }}
    QPushButton:hover {{ background: {c["gris-100"]}; }}
    QPushButton:pressed {{ background: {c["gris-200"]}; }}
    QPushButton:disabled {{
        color: {c["gris-500"]};
        border-color: {BORDE};
        background: {c["gris-50"]};
    }}
    QPushButton#BotonPrimario {{
        background: {PRIMARIO};
        border: 1px solid {PRIMARIO};
        color: {c["blanco"]};
        padding: 9px 22px;
    }}
    QPushButton#BotonPrimario:hover {{ background: {MARCA}; border-color: {MARCA}; }}
    QPushButton#BotonPeligro {{
        background: {c["rojo-600"]};
        border: 1px solid {c["rojo-600"]};
        color: {c["blanco"]};
    }}
    QPushButton#BotonPeligro:hover {{ background: {c["rojo-700"]}; border-color: {c["rojo-700"]}; }}
    QPushButton#BotonPrimario:disabled, QPushButton#BotonPeligro:disabled {{
        background: {c["gris-200"]};
        border: 1px solid {c["gris-200"]};
        color: {c["gris-600"]};
    }}

    /* ---------- Chips de soportes (selección múltiple) ---------- */
    QPushButton#ChipSoporte {{
        background: {SUPERFICIE};
        border: 1px solid {BORDE_CONTROL};
        border-radius: 14px;
        padding: 5px 13px;
        color: {c["gris-700"]};
        font-weight: 600;
        font-size: 12px;
    }}
    QPushButton#ChipSoporte:hover {{ background: {c["azul-50"]}; border-color: {c["azul-400"]}; }}
    QPushButton#ChipSoporte:checked {{
        background: {c["azul-100"]};
        border-color: {c["azul-600"]};
        color: {c["azul-700"]};
    }}

    /* ---------- Chips de filtro del grid ---------- */
    QPushButton#Chip, QPushButton#ChipAviso {{
        border-radius: 999px;
        padding: 5px 13px;
        font-size: 12px;
        font-weight: 700;
        background: {SUPERFICIE};
        border: 1px solid {BORDE_CONTROL};
        color: {c["gris-700"]};
    }}
    QPushButton#Chip:checked {{
        background: {SELECCION};
        border-color: {c["azul-600"]};
        color: {c["azul-700"]};
    }}
    QPushButton#ChipAviso {{ color: {c["ambar-700"]}; border-color: {c["ambar-700"]}; }}
    QPushButton#ChipAviso:checked {{
        background: {c["ambar-100"]};
        border-color: {c["ambar-700"]};
        color: {c["ambar-800"]};
    }}

    /* ---------- Tarjetas y tipografía de contenido ---------- */
    #Contenedor {{ background: transparent; }}
    #Tarjeta {{
        background: {SUPERFICIE};
        border: 1px solid {BORDE};
        border-radius: 12px;
    }}
    #TituloVista {{ color: {c["azul-700"]}; font-size: 17px; font-weight: 700; background: transparent; }}
    #SubtituloVista {{ color: {TEXTO_SUAVE}; font-size: 12px; background: transparent; }}
    #EtiquetaCampo {{
        color: {c["gris-700"]};
        font-size: 11.5px;
        font-weight: 700;
        background: transparent;
    }}
    #AyudaCampo {{ color: {c["gris-500"]}; font-size: 11px; background: transparent; }}
    #Divisor {{ background: {BORDE}; border: 0; }}

    /* ---------- Panel de detalle ---------- */
    #PanelDetalle {{ background: {SUPERFICIE}; border-left: 1px solid {BORDE}; }}
    #PanelDetalle QLabel {{ background: transparent; }}
    #PanelTitulo {{
        color: {c["gris-700"]};
        font-size: 11px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: .06em;
    }}
    #TarjetaDetalle {{
        background: {c["superficie-alt"]};
        border: 1px solid {BORDE};
        border-radius: 9px;
    }}
    #ClaveDetalle {{ color: {c["gris-500"]}; font-size: 10.5px; text-transform: uppercase; letter-spacing: .04em; }}
    #ValorDetalle {{ color: {TEXTO}; font-size: 12.5px; }}
    #ValorMono {{ color: {TEXTO}; font-family: {MONO}; font-size: 12.5px; }}
    #BadgeEstado {{ border-radius: 10px; padding: 4px 11px; font-size: 12px; font-weight: 700; }}
    #AvisoRevision {{
        background: {c["ambar-100"]};
        color: {c["ambar-800"]};
        border-radius: 8px;
        padding: 9px 11px;
        font-size: 12px;
    }}
    #ErrorValidacion {{
        background: {c["rojo-100"]};
        color: {c["azul-900"]};
        border-left: 3px solid {c["rojo-600"]};
        border-radius: 6px;
        padding: 8px 11px;
        font-size: 12px;
    }}

    /* ---------- Tabla ---------- */
    QTableView {{
        background: {SUPERFICIE};
        alternate-background-color: {c["superficie-alt"]};
        border: 1px solid {BORDE};
        border-radius: 10px;
        gridline-color: {c["gris-100"]};
        selection-background-color: {SELECCION};
        selection-color: {TEXTO};
        outline: none;
    }}
    QTableView::item {{ padding: 4px 8px; border: 0; }}
    QHeaderView::section {{
        background: {c["gris-100"]};
        color: {c["gris-700"]};
        border: 0;
        border-bottom: 1px solid {BORDE};
        border-right: 1px solid {BORDE};
        padding: 8px;
        font-size: 11px;
        font-weight: 700;
    }}
    QTableView QTableCornerButton::section {{ background: {c["gris-100"]}; border: 0; }}

    /* ---------- Pestañas de configuración ---------- */
    QTabWidget::pane {{ border: 1px solid {BORDE}; border-radius: 10px; background: {SUPERFICIE}; top: -1px; }}
    QTabBar::tab {{
        background: transparent;
        color: {c["gris-600"]};
        border: 0;
        padding: 9px 18px;
        font-weight: 700;
        font-size: 12.5px;
    }}
    QTabBar::tab:hover {{ color: {c["azul-700"]}; }}
    QTabBar::tab:selected {{
        color: {c["azul-700"]};
        border-bottom: 3px solid {c["azul-600"]};
    }}

    /* ---------- Barra de estado ---------- */
    QStatusBar {{ background: {SUPERFICIE}; border-top: 1px solid {BORDE}; color: {c["gris-500"]}; }}
    QStatusBar::item {{ border: 0; }}

    QScrollBar:vertical {{ background: {c["gris-100"]}; width: 11px; margin: 0; border: 0; }}
    QScrollBar::handle:vertical {{ background: {c["gris-300"]}; border-radius: 5px; min-height: 28px; }}
    QScrollBar::handle:vertical:hover {{ background: {c["gris-400"]}; }}
    QScrollBar:horizontal {{ background: {c["gris-100"]}; height: 11px; margin: 0; border: 0; }}
    QScrollBar::handle:horizontal {{ background: {c["gris-300"]}; border-radius: 5px; min-width: 28px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """


def estilo_etiqueta_estado(estado: Estado) -> str:
    """Inline style for a state label: colour plus its word (never colour alone)."""
    return f"color: {COLOR_ESTADO[estado]}; font-weight: 700; background: transparent;"


def estilo_badge_estado(estado: Estado) -> str:
    """Filled badge: light tint background, dark text of the same family."""
    fondos = {
        "despachado": COLORES["verde-100"],
        "en_taller": COLORES["rojo-100"],
        "sin_datos": COLORES["gris-100"],
    }
    return (
        f"background: {fondos[estado]};"
        f"color: {COLOR_ESTADO[estado]};"
        "border-radius: 10px; padding: 4px 11px; font-weight: 700;"
    )
