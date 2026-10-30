"""Rules of the legacy migration, pinned one by one.

Each test names the rule it protects. If a rule changes, the test that encodes
it must change too — that is the point.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from taller.etl.legacy_csv import (
    canonizar,
    clave_alias,
    corregir_fechas,
    limpiar_codigo_inventario,
    parsear_csv,
    parsear_fecha,
    separar_tecnicos,
)

CSV_REAL = Path(os.environ.get("TALLER_CSV_LEGADO", "/nonexistent"))


class TestParsearFecha:
    def test_parses_the_dotnet_format_with_non_breaking_space(self) -> None:
        assert parsear_fecha("21/9/2022 12:00:00 a.\xa0m.") == dt.date(2022, 9, 21)

    def test_keeps_only_the_date_because_every_source_time_is_midnight(self) -> None:
        assert parsear_fecha("1/2/2024 12:00:00 a. m.") == dt.date(2024, 2, 1)

    def test_empty_becomes_none(self) -> None:
        assert parsear_fecha("") is None
        assert parsear_fecha("   ") is None
        assert parsear_fecha(None) is None

    def test_garbage_raises_instead_of_silently_dropping_the_row(self) -> None:
        with pytest.raises(ValueError, match="unparseable"):
            parsear_fecha("no es una fecha")


class TestCodigoInventario:
    def test_a_leading_o_becomes_a_zero(self) -> None:
        # La institución confirmó el 2026-10-30 que la serie empieza con cero:
        # O2071 es 02071 y OO738 es 00738.
        assert limpiar_codigo_inventario("O2071") == "02071"
        assert limpiar_codigo_inventario("OO738") == "00738"

    def test_the_code_is_completed_to_five_characters(self) -> None:
        assert limpiar_codigo_inventario("1716") == "01716"
        assert limpiar_codigo_inventario("0776") == "00776"

    @pytest.mark.parametrize("marcador", ["N/A", "n/a", "---", "NO", "NO  TIENE", "  "])
    def test_explicit_no_code_markers_become_null(self, marcador: str) -> None:
        assert limpiar_codigo_inventario(marcador) is None

    def test_junk_around_a_numeric_core_is_removed(self) -> None:
        # El código real es 01916; la barra era basura del export.
        assert limpiar_codigo_inventario("01916|") == "01916"

    def test_surrounding_space_is_trimmed(self) -> None:
        assert limpiar_codigo_inventario("  776 ") == "00776"


class TestSepararTecnicos:
    def test_splits_ampersand_slash_and_y(self) -> None:
        assert separar_tecnicos("Herrera & Yohanna") == ("Herrera", "Yohanna")
        assert separar_tecnicos("Ana / Luis / Carlos") == (
            "Ana",
            "Luis",
            "Carlos",
        )
        assert separar_tecnicos("Wagner y Juan Herrera") == ("Wagner", "Juan Herrera")

    def test_na_marker_does_not_invent_technicians(self) -> None:
        # Splitting "N/A" on the slash used to create technicians "N" and "A".
        assert separar_tecnicos("N/A") == ()

    def test_collapses_duplicates_and_preserves_order(self) -> None:
        assert separar_tecnicos("Carlos / carlos / Herrera") == ("Carlos", "Herrera")

    def test_empty_becomes_empty_tuple(self) -> None:
        assert separar_tecnicos("") == ()
        assert separar_tecnicos(None) == ()


class TestCorregirFechas:
    def test_repairs_a_year_typo_when_the_repaired_date_is_close(self) -> None:
        entrada, salida, inferida, revision, motivos = corregir_fechas(
            dt.date(2023, 4, 4), dt.date(2004, 4, 4)
        )
        assert (entrada, salida) == (dt.date(2023, 4, 4), dt.date(2023, 4, 4))
        assert not revision
        assert not inferida
        assert any(m.startswith("salida_reparada") for m in motivos)

    def test_repairs_a_departure_one_year_early(self) -> None:
        _entrada, salida, _inferida, revision, _motivos = corregir_fechas(
            dt.date(2025, 10, 25), dt.date(2024, 10, 28)
        )
        assert salida == dt.date(2025, 10, 28)
        assert not revision

    def test_unexplained_inversion_is_flagged_not_guessed(self) -> None:
        entrada, salida, _inferida, revision, motivos = corregir_fechas(
            dt.date(2022, 12, 1), dt.date(2022, 2, 1)
        )
        assert (entrada, salida) == (dt.date(2022, 12, 1), dt.date(2022, 2, 1))
        assert revision
        assert "salida_anterior_a_entrada_sin_correccion_unica" in motivos

    def test_implausible_year_moves_one_century(self) -> None:
        entrada, _salida, _inferida, _revision, motivos = corregir_fechas(
            dt.date(1023, 3, 1), None
        )
        assert entrada == dt.date(2023, 3, 1)
        assert any(m.startswith("anio_entrada_corregido") for m in motivos)

    def test_missing_intake_is_inferred_from_a_tight_neighbour_window(self) -> None:
        entrada, _salida, inferida, revision, _motivos = corregir_fechas(
            None,
            dt.date(2023, 8, 18),
            vecina_anterior=dt.date(2023, 8, 3),
            vecina_posterior=dt.date(2023, 8, 7),
        )
        assert entrada == dt.date(2023, 8, 7)
        assert inferida
        assert not revision

    def test_same_day_window_is_a_valid_inference(self) -> None:
        entrada, _salida, inferida, _revision, _motivos = corregir_fechas(
            None,
            dt.date(2024, 6, 3),
            vecina_anterior=dt.date(2024, 6, 3),
            vecina_posterior=dt.date(2024, 6, 7),
        )
        assert entrada == dt.date(2024, 6, 3)
        assert inferida

    def test_wide_window_is_flagged_instead_of_inferred(self) -> None:
        entrada, _salida, inferida, revision, motivos = corregir_fechas(
            None,
            dt.date(2023, 12, 5),
            vecina_anterior=dt.date(2023, 10, 4),
            vecina_posterior=dt.date(2023, 12, 19),
        )
        assert entrada is None
        assert not inferida
        assert revision
        assert "sin_fecha_entrada" in motivos

    def test_row_without_any_date_is_flagged(self) -> None:
        entrada, salida, _inferida, revision, motivos = corregir_fechas(None, None)
        assert (entrada, salida) == (None, None)
        assert revision
        assert "sin_fechas" in motivos


class TestAlias:
    def test_accent_and_case_variants_share_a_key(self) -> None:
        assert clave_alias("Agrometeorología") == clave_alias("agrometeorologia")

    def test_most_frequent_spelling_wins(self) -> None:
        canonico = canonizar(["Ana", "ana", "ANA", "Ana"])
        assert canonico[clave_alias("ana")] == "Ana"

    def test_ties_break_alphabetically_so_runs_are_reproducible(self) -> None:
        assert canonizar(["Yohanna", "yohanna"])[clave_alias("yohanna")] == "Yohanna"

    def test_internal_whitespace_collapses(self) -> None:
        assert clave_alias("  Control   de   Calidad ") == "control de calidad"


MINI_CSV = (
    "\ufeffEstado;FechaEntrada;Equipo;Área;Modelo;Inventario;Diagnóstico;FechaSalida;"
    "ServiceTag;Soporte;Nota\n"
    "System.Drawing.Bitmap;21/9/2022 12:00:00 a.\xa0m.;CPU;Agrometeorología;"
    "Dell Vostro 230;776;PC no encendia;21/9/2022 12:00:00 a.\xa0m.;;Luis & Herrera;\n"
    "System.Drawing.Bitmap;22/9/2022 12:00:00 a.\xa0m.;;agrometeorologia;X;N/A;Seteo;;;N/A;\n"
)


class TestParsearCsv:
    def test_reads_rows_and_ignores_the_bitmap_column(self) -> None:
        filas = parsear_csv(MINI_CSV)
        assert len(filas) == 2
        assert filas[0].equipo == "CPU"
        assert filas[0].codigo_inventario == "00776"

    def test_line_numbers_point_at_the_source_file(self) -> None:
        filas = parsear_csv(MINI_CSV)
        assert [f.linea for f in filas] == [2, 3]

    def test_the_bitmap_column_never_reaches_the_model(self) -> None:
        assert not hasattr(parsear_csv(MINI_CSV)[0], "estado")

    def test_missing_columns_are_rejected_loudly(self) -> None:
        with pytest.raises(ValueError, match="missing columns"):
            parsear_csv("Estado;FechaEntrada\nSystem.Drawing.Bitmap;21/9/2022 12:00:00 a. m.\n")


@pytest.mark.skipif(not CSV_REAL.is_file(), reason="legacy CSV not available")
class TestArchivoReal:
    def test_parses_every_row_of_the_real_export(self) -> None:
        filas = parsear_csv(CSV_REAL.read_bytes().decode("utf-8-sig"))
        assert len(filas) == 568

    def test_no_row_is_dropped_for_having_a_bad_date(self) -> None:
        filas = parsear_csv(CSV_REAL.read_bytes().decode("utf-8-sig"))
        # 11 inversions with no single defensible repair, plus 3 intakes that no
        # neighbour bounds tightly. The other 9 missing intakes are inferred.
        assert sum(1 for f in filas if f.requiere_revision) == 14

    def test_exactly_the_documented_nine_intakes_are_inferred(self) -> None:
        filas = parsear_csv(CSV_REAL.read_bytes().decode("utf-8-sig"))
        inferidas = [f.linea for f in filas if f.fecha_entrada_inferida]
        assert inferidas == [134, 146, 156, 170, 213, 242, 304, 321, 396]
