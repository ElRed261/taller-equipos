"""The grid model and the real repository, together.

The unit tests in ``test_ui_model.py`` use a persistence double. This file
proves the seam actually fits: a cell edit travels through the Qt model into the
repository, lands in PostgreSQL, is audited, and the row comes back refreshed.

Runs inside a transaction that is rolled back.
"""

from __future__ import annotations

import datetime as dt

import pytest
from PySide6.QtCore import Qt
from sqlalchemy.orm import Session

from taller.database.repositories import MovimientoRepository
from taller.ui.models.movimientos_table_model import Columna, MovimientosTableModel


@pytest.fixture
def repo(session: Session) -> MovimientoRepository:
    return MovimientoRepository(session)


@pytest.fixture
def modelo(qtbot: object, repo: MovimientoRepository) -> MovimientosTableModel:
    return MovimientosTableModel(repo, usuario="tester", filas=repo.listar(limite=5))


class TestEdicionDesdeElGrid:
    def test_a_cell_edit_reaches_the_database_and_the_audit_trail(
        self, modelo: MovimientosTableModel, repo: MovimientoRepository
    ) -> None:
        original = modelo.fila(0)
        assert modelo.setData(modelo.index(0, Columna.NOTA), "nota desde el grid")

        assert modelo.fila(0).nota == "nota desde el grid"
        historial = repo.historial(original.id)
        assert historial[0]["campo"] == "nota"
        assert historial[0]["valor_nuevo"] == "nota desde el grid"
        assert historial[0]["usuario"] == "tester"

    def test_clearing_the_departure_date_updates_the_badge(
        self, qtbot: object, repo: MovimientoRepository
    ) -> None:
        # The newest movements are still in the workshop, so the model is fed
        # with dispatched rows explicitly instead of assuming the first row.
        despachados = repo.listar(estado="despachado", limite=1)
        modelo = MovimientosTableModel(repo, usuario="tester", filas=despachados)
        indice_estado = modelo.index(0, Columna.ESTADO)
        assert modelo.data(indice_estado, Qt.ItemDataRole.UserRole) == "despachado"

        assert modelo.setData(modelo.index(0, Columna.FECHA_SALIDA), None)

        assert modelo.data(indice_estado, Qt.ItemDataRole.UserRole) == "en_taller"

    def test_the_database_still_refuses_an_inverted_date(
        self, qtbot: object, modelo: MovimientosTableModel, repo: MovimientoRepository
    ) -> None:
        fila = next(
            modelo.fila(numero)
            for numero in range(modelo.rowCount())
            if modelo.fila(numero).fecha_entrada
        )
        posicion = modelo.indice_de(fila.id)
        assert posicion is not None and fila.fecha_entrada is not None
        antes = modelo.fila(posicion)
        auditorias_antes = len(repo.historial(fila.id))

        with qtbot.waitSignal(modelo.error_validacion, timeout=1000) as señal:  # type: ignore[attr-defined]
            assert (
                modelo.setData(
                    modelo.index(posicion, Columna.FECHA_SALIDA),
                    fila.fecha_entrada - dt.timedelta(days=5),
                )
                is False
            )

        assert "no puede ser anterior" in señal.args[0]
        assert modelo.fila(posicion) == antes
        assert len(repo.historial(fila.id)) == auditorias_antes

    def test_choosing_a_catalog_row_writes_the_identifier(
        self, modelo: MovimientosTableModel, session: Session
    ) -> None:
        from sqlalchemy import select

        from taller.database.models import Area

        nueva_area = session.scalar(select(Area.id).where(Area.nombre == "Contabilidad"))
        assert nueva_area is not None

        assert modelo.setData(modelo.index(0, Columna.AREA), nueva_area)
        assert modelo.fila(0).area == "Contabilidad"

    def test_clearing_a_catalog_reference_is_allowed(self, modelo: MovimientosTableModel) -> None:
        assert modelo.setData(modelo.index(0, Columna.AREA), None)
        assert modelo.fila(0).area is None
