"""Cell editors and painters for the movements grid.

Each delegate exists to stop a specific kind of garbage:

* ``SemaforoDelegate`` — paints the derived state as a badge; the cell is not
  editable, so the indicator cannot be faked.
* ``ComboDelegate`` — areas and equipment types can only be picked from the
  catalog, which is how the 190 spellings became 119 rows and stay 119.
* ``FechaDelegate`` — a calendar with ``dd/mm/aaaa`` and an explicit empty
  value, so "sin fecha" is expressible without typing ``N/A``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDateEdit,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from taller.schemas.movimiento import CatalogoLeido
from taller.ui.models.movimientos_table_model import COLOR_ESTADO, Columna

#: Sentinel shown as an em dash meaning "no date". A QDateEdit cannot be empty,
#: so the minimum date carries that meaning instead.
FECHA_VACIA = QDate(1900, 1, 1)
TEXTO_SIN_FECHA = "—"


class SemaforoDelegate(QStyledItemDelegate):
    """Draws one filled circle: green dispatched, red in the workshop, grey unknown."""

    def paint(
        self, painter: QPainter, option: QStyleOptionViewItem, index: object
    ) -> None:
        opcion = QStyleOptionViewItem(option)
        self.initStyleOption(opcion, index)  # type: ignore[arg-type]
        opcion.text = ""
        opcion.icon = opcion.icon.__class__()
        estilo = opcion.widget.style() if opcion.widget else QApplication.style()
        estilo.drawControl(QStyle.ControlElement.CE_ItemViewItem, opcion, painter, opcion.widget)

        estado = index.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        color = COLOR_ESTADO.get(estado)  # type: ignore[arg-type]
        if color is None:
            return

        diameter = 12
        rect = opcion.rect
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(
            rect.center().x() - diameter // 2,
            rect.center().y() - diameter // 2,
            diameter,
            diameter,
        )
        painter.restore()


class ComboDelegate(QStyledItemDelegate):
    """Edits a foreign key by picking a catalog row, never by typing a name."""

    def __init__(
        self,
        proveedor: Callable[[], Sequence[CatalogoLeido]],
        *,
        permite_vacio: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._proveedor = proveedor
        self._permite_vacio = permite_vacio

    def createEditor(  # noqa: N802
        self, parent: QWidget, option: QStyleOptionViewItem, index: object
    ) -> QWidget:
        combo = QComboBox(parent)
        if self._permite_vacio:
            combo.addItem("(sin asignar)", None)
        for fila in self._proveedor():
            combo.addItem(fila.nombre, fila.id)
        return combo

    def setEditorData(self, editor: QWidget, index: object) -> None:  # noqa: N802
        if not isinstance(editor, QComboBox):
            return
        actual = index.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        posicion = editor.findData(actual)
        editor.setCurrentIndex(max(posicion, 0))

    def setModelData(  # noqa: N802
        self, editor: QWidget, model: object, index: object
    ) -> None:
        if not isinstance(editor, QComboBox):
            return
        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)  # type: ignore[attr-defined]


class FechaDelegate(QStyledItemDelegate):
    """Calendar editor in ``dd/mm/aaaa`` with an explicit "no date" value."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    def createEditor(  # noqa: N802
        self, parent: QWidget, option: QStyleOptionViewItem, index: object
    ) -> QWidget:
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        editor.setDisplayFormat("dd/MM/yyyy")
        editor.setMinimumDate(FECHA_VACIA)
        editor.setSpecialValueText(TEXTO_SIN_FECHA)
        return editor

    def setEditorData(self, editor: QWidget, index: object) -> None:  # noqa: N802
        if not isinstance(editor, QDateEdit):
            return
        valor = index.data(Qt.ItemDataRole.UserRole)  # type: ignore[attr-defined]
        if valor is None:
            editor.setDate(FECHA_VACIA)
            return
        if hasattr(valor, "year"):
            editor.setDate(QDate(valor.year, valor.month, valor.day))

    def setModelData(  # noqa: N802
        self, editor: QWidget, model: object, index: object
    ) -> None:
        if not isinstance(editor, QDateEdit):
            return
        fecha = editor.date()
        valor = None if fecha == FECHA_VACIA else fecha.toPython()
        model.setData(index, valor, Qt.ItemDataRole.EditRole)  # type: ignore[attr-defined]


def delegate_por_columna(
    columna: Columna,
    *,
    areas: Callable[[], Sequence[CatalogoLeido]],
    tipos: Callable[[], Sequence[CatalogoLeido]],
) -> QStyledItemDelegate | None:
    """Pick the right editor for a column, or ``None`` for the default text one."""
    if columna is Columna.ESTADO:
        return SemaforoDelegate()
    if columna is Columna.AREA:
        return ComboDelegate(areas, permite_vacio=True)
    if columna is Columna.TIPO:
        return ComboDelegate(tipos, permite_vacio=True)
    if columna in {Columna.FECHA_ENTRADA, Columna.FECHA_SALIDA}:
        return FechaDelegate()
    return None
