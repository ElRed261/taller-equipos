"""Qt table model for movements.

The model never queries the database. It holds DTOs produced by the repository
and asks an injected persistence object to save edits, which is what makes it
testable without a database and safe to run on the GUI thread.

Editing is optimistic but reversible: ``setData`` writes through the repository
and replaces the row with the DTO the repository returns. If the write fails,
the row is untouched and ``error_validacion`` carries a message the view can
show. Nothing is ever written that the database would refuse.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Protocol

from pydantic import ValidationError
from PySide6.QtCore import QAbstractTableModel, QDate, QModelIndex, QObject, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

from taller.formato import parsear_fecha_usuario
from taller.schemas.movimiento import (
    Estado,
    FechasInvalidas,
    MovimientoActualizar,
    MovimientoLeido,
)

#: Badge colours for the derived state. Shared with the delegate so the circle
#: looks the same whether it is painted by the model's icon or by the delegate.
COLOR_ESTADO: dict[Estado, str] = {
    "despachado": "#2E7D32",
    "en_taller": "#C62828",
    "sin_datos": "#757575",
}

ETIQUETA_ESTADO: dict[Estado, str] = {
    "despachado": "Despachado",
    "en_taller": "En taller",
    "sin_datos": "Sin datos",
}


class PersistenciaMovimientos(Protocol):
    """The only data capability the model needs.

    Declaring it here keeps this module free of SQLAlchemy: the real
    ``MovimientoRepository`` satisfies it, and a test double satisfies it too.
    """

    def actualizar(
        self, movimiento_id: int, cambios: MovimientoActualizar, *, usuario: str
    ) -> MovimientoLeido: ...


class Columna(IntEnum):
    ESTADO = 0
    FECHA_ENTRADA = 1
    FECHA_SALIDA = 2
    AREA = 3
    TIPO = 4
    MODELO = 5
    INVENTARIO = 6
    SERVICE_TAG = 7
    DIAGNOSTICO = 8
    SOPORTE = 9
    NOTA = 10
    REVISION = 11


@dataclass(frozen=True)
class DefinicionColumna:
    titulo: str
    campo: str | None
    editable: bool = False
    centrada: bool = False


#: Column order is part of the public contract of the grid: the view, the
#: delegates and the tests all index it. The first column is the indicator.
COLUMNAS: tuple[DefinicionColumna, ...] = (
    DefinicionColumna("", None, editable=False, centrada=True),
    DefinicionColumna("Entrada", "fecha_entrada", editable=True, centrada=True),
    DefinicionColumna("Salida", "fecha_salida", editable=True, centrada=True),
    DefinicionColumna("Área", "area_id", editable=True),
    DefinicionColumna("Equipo", "tipo_equipo_id", editable=True),
    DefinicionColumna("Modelo", "modelo", editable=True),
    DefinicionColumna("Inventario", "codigo_inventario", editable=True),
    DefinicionColumna("Service Tag", "service_tag", editable=True),
    DefinicionColumna("Diagnóstico", "diagnostico", editable=True),
    DefinicionColumna("Soporte", None, editable=False),
    DefinicionColumna("Nota", "nota", editable=True),
    DefinicionColumna("⚠", None, editable=False, centrada=True),
)

assert len(COLUMNAS) == len(Columna), "cada columna necesita su definición"


class MovimientosTableModel(QAbstractTableModel):
    """Read-mostly table of movements, editable cell by cell."""

    error_validacion = Signal(str)
    movimiento_actualizado = Signal(int)

    def __init__(
        self,
        persistencia: PersistenciaMovimientos,
        *,
        usuario: str,
        filas: Sequence[MovimientoLeido] = (),
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if not usuario.strip():
            raise ValueError("hace falta un usuario para atribuir las ediciones")
        self._persistencia = persistencia
        self._usuario = usuario
        self._filas: list[MovimientoLeido] = list(filas)
        self._iconos: dict[Estado, QIcon] = {
            estado: _icono_punto(color) for estado, color in COLOR_ESTADO.items()
        }

    # ------------------------------------------------------------- Qt overrides

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(self._filas)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802
        return 0 if parent is not None and parent.isValid() else len(COLUMNAS)

    def headerData(  # noqa: N802
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return COLUMNAS[section].titulo
        return section + 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if COLUMNAS[index.column()].editable:
            return base | Qt.ItemFlag.ItemIsEditable
        return base

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        fila = self._filas[index.row()]
        columna = Columna(index.column())

        if role == Qt.ItemDataRole.DecorationRole and columna is Columna.ESTADO:
            return self._iconos[fila.estado]
        if role == Qt.ItemDataRole.DisplayRole:
            return self._texto(fila, columna)
        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(fila, columna)
        if role == Qt.ItemDataRole.TextAlignmentRole and COLUMNAS[index.column()].centrada:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.ForegroundRole and columna is Columna.REVISION:
            return QColor("#B26A00") if fila.requiere_revision else None
        if role == Qt.ItemDataRole.UserRole:
            return self._valor_orden(fila, columna)
        return None

    def setData(  # noqa: N802
        self, index: QModelIndex, value: Any, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        definicion = COLUMNAS[index.column()]
        if not definicion.editable or definicion.campo is None:
            return False

        fila = self._filas[index.row()]
        try:
            valor = self._a_modelo(definicion.campo, value)
            cambios = MovimientoActualizar(**{definicion.campo: valor})
        except (ValidationError, ValueError) as exc:
            self.error_validacion.emit(_mensaje(exc))
            return False

        try:
            actualizada = self._persistencia.actualizar(fila.id, cambios, usuario=self._usuario)
        except FechasInvalidas as exc:
            self.error_validacion.emit(str(exc))
            return False
        except ValidationError as exc:
            self.error_validacion.emit(_mensaje(exc))
            return False

        self._filas[index.row()] = actualizada
        self.dataChanged.emit(
            self.index(index.row(), 0),
            self.index(index.row(), len(COLUMNAS) - 1),
        )
        self.movimiento_actualizado.emit(actualizada.id)
        return True

    # ------------------------------------------------------------ extra API

    def reemplazar(self, filas: Sequence[MovimientoLeido]) -> None:
        """Swap the whole contents, e.g. after a search or a reload."""
        self.beginResetModel()
        self._filas = list(filas)
        self.endResetModel()

    def insertar_fila(self, fila: MovimientoLeido, posicion: int = 0) -> None:
        """Add one row without reloading the table.

        Registering happens on the form (the home screen), so the grid must learn
        about the new row without the user switching pages first.
        """
        posicion = max(0, min(posicion, len(self._filas)))
        self.beginInsertRows(QModelIndex(), posicion, posicion)
        self._filas.insert(posicion, fila)
        self.endInsertRows()

    def actualizar_fila(self, fila: MovimientoLeido) -> bool:
        """Replace one row in place, for changes made outside the grid.

        Used by "marcar salida" and "marcar revisado": reloading all 568 rows for
        one change would lose the scroll position and the selection.
        """
        posicion = self.indice_de(fila.id)
        if posicion is None:
            return False
        self._filas[posicion] = fila
        self.dataChanged.emit(
            self.index(posicion, 0),
            self.index(posicion, self.columnCount() - 1),
        )
        return True

    def fila(self, numero: int) -> MovimientoLeido:
        return self._filas[numero]

    def filas(self) -> tuple[MovimientoLeido, ...]:
        return tuple(self._filas)

    def indice_de(self, movimiento_id: int) -> int | None:
        for numero, fila in enumerate(self._filas):
            if fila.id == movimiento_id:
                return numero
        return None

    def columna(self, nombre: Columna) -> int:
        return int(nombre)

    # -------------------------------------------------------------- internals

    @staticmethod
    def _texto(fila: MovimientoLeido, columna: Columna) -> str:
        if columna is Columna.ESTADO:
            return ""  # the badge speaks; text would fight the icon
        if columna is Columna.FECHA_ENTRADA:
            return fila.fecha_entrada_texto
        if columna is Columna.FECHA_SALIDA:
            return fila.fecha_salida_texto
        if columna is Columna.AREA:
            return fila.area or ""
        if columna is Columna.TIPO:
            return fila.tipo_equipo or ""
        if columna is Columna.MODELO:
            return fila.modelo or ""
        if columna is Columna.INVENTARIO:
            return fila.codigo_inventario or ""
        if columna is Columna.SERVICE_TAG:
            return fila.service_tag or ""
        if columna is Columna.DIAGNOSTICO:
            return fila.diagnostico or ""
        if columna is Columna.SOPORTE:
            return ", ".join(fila.soporte)
        if columna is Columna.NOTA:
            return fila.nota or ""
        if columna is Columna.REVISION:
            return "⚠" if fila.requiere_revision else ""
        return ""

    @staticmethod
    def _tooltip(fila: MovimientoLeido, columna: Columna) -> str | None:
        if columna is Columna.ESTADO:
            base = ETIQUETA_ESTADO[fila.estado]
            if fila.estado == "despachado":
                return f"{base} el {fila.fecha_salida_texto}"
            if fila.estado == "en_taller":
                return f"{base} desde el {fila.fecha_entrada_texto}"
            return f"{base}: el registro no tiene fechas"
        if columna is Columna.REVISION and fila.requiere_revision:
            motivos = ["Marcado para revisión durante la migración."]
            if fila.fecha_entrada_inferida:
                motivos.append("La fecha de entrada fue inferida por vecindad.")
            return " ".join(motivos)
        if columna is Columna.SOPORTE and len(fila.soporte) > 1:
            return "Principal: " + fila.soporte[0]
        return None

    @staticmethod
    def _valor_orden(fila: MovimientoLeido, columna: Columna) -> Any:
        """Raw value the proxy sorts on. ``None`` always sorts last."""
        if columna is Columna.ESTADO:
            return fila.estado
        if columna is Columna.FECHA_ENTRADA:
            return fila.fecha_entrada
        if columna is Columna.FECHA_SALIDA:
            return fila.fecha_salida
        if columna is Columna.AREA:
            return fila.area or ""
        if columna is Columna.TIPO:
            return fila.tipo_equipo or ""
        if columna is Columna.MODELO:
            return fila.modelo or ""
        if columna is Columna.INVENTARIO:
            return fila.codigo_inventario or ""
        if columna is Columna.SERVICE_TAG:
            return fila.service_tag or ""
        if columna is Columna.DIAGNOSTICO:
            return fila.diagnostico or ""
        if columna is Columna.SOPORTE:
            return ", ".join(fila.soporte)
        if columna is Columna.NOTA:
            return fila.nota or ""
        return int(fila.requiere_revision)

    @staticmethod
    def _a_modelo(campo: str, valor: Any) -> Any:
        """Convert what a delegate hands back into what the schema expects."""
        if campo in {"fecha_entrada", "fecha_salida"}:
            return _a_fecha(valor)
        if campo in {"area_id", "tipo_equipo_id"}:
            if valor is None or valor == "" or valor == -1:
                return None
            return int(valor)
        if isinstance(valor, str):
            return valor
        return None if valor is None else str(valor)


def _a_fecha(valor: Any) -> dt.date | None:
    """Accept a ``date``, a ``datetime``, a ``QDate`` or ``dd/mm/aaaa`` text."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, dt.datetime):
        return valor.date()
    if isinstance(valor, dt.date):
        return valor
    if isinstance(valor, QDate):
        return None if not valor.isValid() else dt.date(valor.year(), valor.month(), valor.day())
    if isinstance(valor, str):
        return parsear_fecha_usuario(valor)
    raise ValueError(f"fecha no reconocida: {valor!r}")


def _mensaje(exc: Exception) -> str:
    """Turn a Pydantic error into one line a technician can act on."""
    if isinstance(exc, ValidationError):
        primero = exc.errors()[0]
        return str(primero.get("msg", "dato inválido")).removeprefix("Value error, ")
    return str(exc)


def _icono_punto(color: str, diametro: int = 12) -> QIcon:
    """A filled circle, antialiased, used for the state column."""
    pixmap = QPixmap(diametro, diametro)
    pixmap.fill(Qt.GlobalColor.transparent)
    pintor = QPainter(pixmap)
    pintor.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pintor.setPen(Qt.PenStyle.NoPen)
    pintor.setBrush(QColor(color))
    pintor.drawEllipse(1, 1, diametro - 2, diametro - 2)
    pintor.end()
    return QIcon(pixmap)
