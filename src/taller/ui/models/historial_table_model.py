"""Modelo de la tabla de historial de catálogo.

Lista filas planas de ``CatalogoRepository.historial()``. Es de solo lectura: el
historial es un registro, no una pantalla de edición.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

COLUMNAS = ("Cuándo", "Catálogo", "Acción", "Antes", "Después", "Quién")

NOMBRES = {
    "area": "Área",
    "tecnico": "Técnico",
    "tipo_equipo": "Tipo de equipo",
}

ACCIONES = {
    "crear": "Creó",
    "renombrar": "Renombró",
    "activar": "Activó",
    "desactivar": "Desactivó",
    "fusionar": "Fusionó",
}


class HistorialTableModel(QAbstractTableModel):
    """Filas del historial de catálogo, lo más nuevo primero."""

    def __init__(self, filas: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._filas = filas or []

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(self._filas)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        if parent is not None and parent.isValid():
            return 0
        return len(COLUMNAS)

    def headerData(  # noqa: N802
        self,
        seccion: int,
        orientacion: Qt.Orientation,
        rol: int = Qt.ItemDataRole.DisplayRole,
    ):
        if orientacion == Qt.Orientation.Horizontal and rol == Qt.ItemDataRole.DisplayRole:
            return COLUMNAS[seccion]
        return None

    def data(self, indice: QModelIndex, rol: int = Qt.ItemDataRole.DisplayRole):
        if not indice.isValid():
            return None
        fila = self._filas[indice.row()]
        columna = indice.column()
        if rol == Qt.ItemDataRole.DisplayRole:
            if columna == 0:
                momento = fila.get("ocurrido_en")
                return momento.astimezone().strftime("%d/%m/%Y %H:%M") if momento else ""
            if columna == 1:
                return NOMBRES.get(str(fila.get("catalogo")), str(fila.get("catalogo")))
            if columna == 2:
                accion = str(fila.get("accion"))
                nombre = ACCIONES.get(accion, accion)
                campo = str(fila.get("campo") or "")
                # El campo solo aporta cuando la acción no alcanza para entenderla.
                if campo in ("nombre", "activo", "fusionado_en", "referencias_movidas"):
                    return nombre
                return f"{nombre} · {campo}" if campo else nombre
            if columna == 3:
                return "" if fila.get("valor_anterior") is None else str(fila["valor_anterior"])
            if columna == 4:
                return "" if fila.get("valor_nuevo") is None else str(fila["valor_nuevo"])
            if columna == 5:
                return str(fila.get("usuario") or "")
        return None

    def reemplazar(self, filas: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._filas = list(filas)
        self.endResetModel()
