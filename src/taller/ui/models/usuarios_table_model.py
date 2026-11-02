"""Modelo de la tabla de usuarios.

Model/View como el resto de la aplicación: la vista no guarda datos, solo pide
celdas. El hash de la contraseña no está en el DTO, así que no hay forma de que
llegue a la pantalla por descuido.
"""

from __future__ import annotations

import datetime as dt

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from taller.schemas.usuario import UsuarioLeido

COLUMNAS = ("Usuario", "Estado", "Rol", "Último acceso")


class UsuariosTableModel(QAbstractTableModel):
    """Filas de ``UsuarioLeido`` en una tabla de solo lectura."""

    def __init__(self, filas: list[UsuarioLeido] | None = None) -> None:
        super().__init__()
        self._filas: list[UsuarioLeido] = filas or []

    # ------------------------------------------------------------------ Qt API

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
                return fila.nombre
            if columna == 1:
                return "Activo" if fila.activo else "Inactivo"
            if columna == 2:
                return "Administrador" if fila.es_admin else "Operador"
            if columna == 3:
                if fila.ultimo_acceso is None:
                    return "nunca"
                return fila.ultimo_acceso.astimezone().strftime("%d/%m/%Y %H:%M")
        if rol == Qt.ItemDataRole.TextAlignmentRole and columna == 3:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    # --------------------------------------------------------------- interfaz

    def reemplazar(self, filas: list[UsuarioLeido]) -> None:
        self.beginResetModel()
        self._filas = list(filas)
        self.endResetModel()

    def fila(self, posicion: int) -> UsuarioLeido | None:
        if 0 <= posicion < len(self._filas):
            return self._filas[posicion]
        return None

    def ahora(self) -> dt.datetime:
        return dt.datetime.now(dt.UTC)
