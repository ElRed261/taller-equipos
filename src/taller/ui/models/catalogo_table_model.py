"""Table model for one catalog (areas, equipment types, technicians).

Small but a real model on purpose: the project rule says tables go through
``QAbstractTableModel`` so they stay testable without a widget, and a
``QTableWidget`` would hide the merge logic inside the view.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import IntEnum
from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, Qt
from PySide6.QtGui import QColor

from taller.schemas.movimiento import CatalogoConUso


class ColumnaCatalogo(IntEnum):
    NOMBRE = 0
    ESTADO = 1
    MOVIMIENTOS = 2


ENCABEZADOS = ("Nombre", "Estado", "Movimientos")


class CatalogoTableModel(QAbstractTableModel):
    def __init__(
        self,
        filas: Sequence[CatalogoConUso] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._filas: list[CatalogoConUso] = list(filas)

    # ------------------------------------------------------------ Qt overrides

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self._filas)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(ENCABEZADOS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return ENCABEZADOS[section]
        return section + 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        fila = self._filas[index.row()]
        columna = ColumnaCatalogo(index.column())

        if role == Qt.ItemDataRole.DisplayRole:
            if columna is ColumnaCatalogo.NOMBRE:
                return fila.nombre
            if columna is ColumnaCatalogo.ESTADO:
                return "Activo" if fila.activo else "Inactivo"
            return str(fila.movimientos)

        if role == Qt.ItemDataRole.ForegroundRole:
            if columna is ColumnaCatalogo.ESTADO and not fila.activo:
                return QColor("#6B7684")
            if columna is ColumnaCatalogo.MOVIMIENTOS:
                return QColor("#55606F")
            return None

        if role == Qt.ItemDataRole.TextAlignmentRole and columna is ColumnaCatalogo.MOVIMIENTOS:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        if role == Qt.ItemDataRole.UserRole:
            return fila.id

        if role == Qt.ItemDataRole.ToolTipRole and fila.movimientos:
            plural = "movimiento" if fila.movimientos == 1 else "movimientos"
            return f"{fila.movimientos} {plural} dependen de «{fila.nombre}»"
        return None

    # ---------------------------------------------------------------- extra API

    def reemplazar(self, filas: Sequence[CatalogoConUso]) -> None:
        self.beginResetModel()
        self._filas = list(filas)
        self.endResetModel()

    def fila(self, posicion: int) -> CatalogoConUso:
        return self._filas[posicion]

    def filas(self) -> tuple[CatalogoConUso, ...]:
        return tuple(self._filas)

    def ids_por_nombre(self, nombre: str) -> list[CatalogoConUso]:
        return [fila for fila in self._filas if fila.nombre == nombre]
