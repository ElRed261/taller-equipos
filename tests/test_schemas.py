"""The validation boundary: what a widget is allowed to send, and what it gets back."""

from __future__ import annotations

import datetime as dt

import pytest
from pydantic import ValidationError

from taller.schemas.movimiento import (
    FechasInvalidas,
    MovimientoActualizar,
    MovimientoCrear,
    MovimientoLeido,
    ResumenEstados,
    validar_orden_fechas,
)


class TestCamposEditables:
    def test_text_is_trimmed_and_inner_whitespace_collapsed(self) -> None:
        datos = MovimientoCrear(modelo="  Dell   Optiplex   3050 ")
        assert datos.modelo == "Dell Optiplex 3050"

    def test_blank_text_becomes_none_not_empty_string(self) -> None:
        datos = MovimientoCrear(nota="   ", diagnostico="")
        assert datos.nota is None
        assert datos.diagnostico is None

    def test_missing_fields_default_to_none(self) -> None:
        datos = MovimientoCrear()
        assert datos.fecha_entrada is None
        assert datos.area_id is None

    def test_derived_and_provenance_fields_cannot_be_written(self) -> None:
        with pytest.raises(ValidationError):
            MovimientoCrear.model_validate({"requiere_revision": True})
        with pytest.raises(ValidationError):
            MovimientoCrear.model_validate({"origen": "csv_v1"})
        with pytest.raises(ValidationError):
            MovimientoCrear.model_validate({"estado": "despachado"})


class TestCodigoInventario:
    def test_a_leading_o_becomes_a_zero(self) -> None:
        # Confirmado por la institución: la serie empieza con cero.
        assert MovimientoCrear(codigo_inventario=" O2071 ").codigo_inventario == "02071"
        assert MovimientoCrear(codigo_inventario="OO738").codigo_inventario == "00738"

    def test_the_code_is_completed_to_five_characters(self) -> None:
        # La regla que pidió el usuario: 1716 es 01716 y 0776 también.
        assert MovimientoCrear(codigo_inventario="1716").codigo_inventario == "01716"
        assert MovimientoCrear(codigo_inventario="0776").codigo_inventario == "00776"

    def test_no_code_markers_become_null(self) -> None:
        assert MovimientoCrear(codigo_inventario="N/A").codigo_inventario is None
        assert MovimientoCrear(codigo_inventario="NO  TIENE").codigo_inventario is None


class TestOrdenDeFechas:
    def test_a_normal_range_is_accepted(self) -> None:
        datos = MovimientoCrear(
            fecha_entrada=dt.date(2024, 1, 10), fecha_salida=dt.date(2024, 1, 15)
        )
        assert datos.fecha_salida == dt.date(2024, 1, 15)

    def test_the_same_day_is_accepted(self) -> None:
        MovimientoCrear(fecha_entrada=dt.date(2024, 1, 10), fecha_salida=dt.date(2024, 1, 10))

    def test_the_helper_rejects_with_both_dates_in_dd_mm_aaaa(self) -> None:
        with pytest.raises(FechasInvalidas) as error:
            validar_orden_fechas(dt.date(2024, 1, 10), dt.date(2024, 1, 5))
        mensaje = str(error.value)
        assert "05/01/2024" in mensaje
        assert "10/01/2024" in mensaje

    def test_the_schema_shape_does_not_police_order_by_itself(self) -> None:
        # Deliberate: raising inside a model_validator makes Pydantic wrap the
        # error in a ValidationError, and the UI could no longer tell a date
        # inversion from a type error. The repository validates before writing.
        datos = MovimientoCrear(
            fecha_entrada=dt.date(2024, 1, 10), fecha_salida=dt.date(2024, 1, 5)
        )
        assert datos.fecha_salida == dt.date(2024, 1, 5)

    def test_the_helper_is_usable_without_the_schema(self) -> None:
        # The repository calls it after merging a partial edit with the stored row.
        validar_orden_fechas(None, dt.date(2024, 1, 5))
        validar_orden_fechas(dt.date(2024, 1, 5), None)
        with pytest.raises(FechasInvalidas):
            validar_orden_fechas(dt.date(2024, 1, 10), dt.date(2024, 1, 5))


class TestActualizacionParcial:
    def test_absent_fields_are_absent_not_none(self) -> None:
        cambios = MovimientoActualizar(nota="revisado")
        assert cambios.model_dump(exclude_unset=True) == {"nota": "revisado"}

    def test_an_explicit_none_means_clear_this_field(self) -> None:
        cambios = MovimientoActualizar(nota=None)
        assert cambios.model_dump(exclude_unset=True) == {"nota": None}

    def test_an_edit_does_not_validate_order_on_its_own(self) -> None:
        # A lone new departure date cannot be validated without the stored intake
        # date; the repository validates the merged result instead.
        cambios = MovimientoActualizar(fecha_salida=dt.date(2024, 1, 5))
        assert cambios.fecha_salida == dt.date(2024, 1, 5)


class TestMovimientoLeido:
    def _fila(self, **extra: object) -> MovimientoLeido:
        base: dict[str, object] = {"id": 1, "estado": "despachado"}
        base.update(extra)
        return MovimientoLeido.model_validate(base)

    def test_dates_are_exposed_as_dd_mm_aaaa(self) -> None:
        fila = self._fila(fecha_entrada=dt.date(2022, 9, 21), fecha_salida=None)
        assert fila.fecha_entrada_texto == "21/09/2022"
        assert fila.fecha_salida_texto == ""
        assert ":" not in fila.fecha_entrada_texto

    def test_the_search_key_is_accent_and_case_insensitive(self) -> None:
        fila = self._fila(area="Agrometeorología", modelo="Dell Optiplex 3050")
        assert "agrometeorologia" in fila.texto_busqueda
        assert "dell optiplex" in fila.texto_busqueda

    def test_the_search_key_includes_technician_names(self) -> None:
        fila = self._fila(soporte=["Luis Suarez", "Herrera"])
        assert "luis suarez" in fila.texto_busqueda
        assert "herrera" in fila.texto_busqueda

    def test_no_search_key_for_an_empty_row(self) -> None:
        assert self._fila().texto_busqueda == ""


class TestResumen:
    def test_total_sums_the_three_states(self) -> None:
        resumen = ResumenEstados(en_taller=135, despachado=431, sin_datos=2, pendientes_revision=14)
        assert resumen.total == 568
