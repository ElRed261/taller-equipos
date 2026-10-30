"""Search and filter proxy for the movements grid.

Filtering happens in memory over ``MovimientoLeido.texto_busqueda``, which is
already accent- and case-normalised. That is the deliberate choice from S7: 568
rows (and even tens of thousands) filter in well under a millisecond, and no
database round trip can make the grid stutter while a technician types.

Search semantics: every token must appear somewhere. ``dvd agromet`` finds the
DVD drive from Agrometeorología, which is how people actually search.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PySide6.QtCore import QModelIndex, QSortFilterProxyModel, Qt

from taller.schemas.movimiento import Estado
from taller.texto import clave_alias
from taller.ui.models.movimientos_table_model import MovimientoLeido, MovimientosTableModel


class FiltroMovimientos(QSortFilterProxyModel):
    """Multi-criteria filter: free text, state, and pending review."""

    def __init__(self, parent: Any = None) -> None:
        super().__init__(parent)
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.setDynamicSortFilter(True)
        self._tokens: tuple[str, ...] = ()
        self._estado: Estado | None = None
        self._solo_revision = False

    # ------------------------------------------------------------- API

    def set_texto(self, texto: str) -> None:
        tokens = tuple(token for token in clave_alias(texto).split(" ") if token)
        if tokens == self._tokens:
            return
        self.beginFilterChange()
        self._tokens = tokens
        self.endFilterChange()

    def set_estado(self, estado: Estado | None) -> None:
        if estado == self._estado:
            return
        self.beginFilterChange()
        self._estado = estado
        self.endFilterChange()

    def set_solo_revision(self, solo_revision: bool) -> None:
        if solo_revision == self._solo_revision:
            return
        self.beginFilterChange()
        self._solo_revision = solo_revision
        self.endFilterChange()

    @property
    def texto(self) -> tuple[str, ...]:
        return self._tokens

    # ------------------------------------------------------- Qt overrides

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        modelo = self.sourceModel()
        if not isinstance(modelo, MovimientosTableModel):
            return True
        fila = modelo.fila(source_row)

        if self._estado is not None and fila.estado != self._estado:
            return False
        if self._solo_revision and not fila.requiere_revision:
            return False
        if self._tokens:
            pajar = fila.texto_busqueda
            if not all(token in pajar for token in self._tokens):
                return False
        return True

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802
        """Sort by the raw value, always pushing empty cells to the bottom.

        Sorting dates as text would put ``01/02/2024`` before ``31/12/2023``;
        that is why the model exposes the real value in ``UserRole``.
        """
        izquierda = self.sourceModel().data(left, Qt.ItemDataRole.UserRole)
        derecha = self.sourceModel().data(right, Qt.ItemDataRole.UserRole)
        return _menor_que(izquierda, derecha)


def _menor_que(izquierda: Any, derecha: Any) -> bool:
    if izquierda is None or izquierda == "":
        return False
    if derecha is None or derecha == "":
        return True
    try:
        return bool(izquierda < derecha)
    except TypeError:
        return str(izquierda) < str(derecha)


def filtrar(
    filas: Sequence[MovimientoLeido],
    *,
    texto: str = "",
    estado: Estado | None = None,
    solo_revision: bool = False,
) -> list[MovimientoLeido]:
    """Same rules as the proxy, without Qt. Used by tests and by non-UI callers."""
    tokens = tuple(token for token in clave_alias(texto).split(" ") if token)
    salida: list[MovimientoLeido] = []
    for fila in filas:
        if estado is not None and fila.estado != estado:
            continue
        if solo_revision and not fila.requiere_revision:
            continue
        if tokens and not all(token in fila.texto_busqueda for token in tokens):
            continue
        salida.append(fila)
    return salida
