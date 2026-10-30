"""The date format requirement: ``dd/mm/aaaa``, never hours.

These tests exist because the requirement has two halves that are easy to lose
separately: the database must not store a time (pinned in the schema tests) and
what the user reads must not show one (pinned here).
"""

from __future__ import annotations

import datetime as dt

import pytest

from taller.formato import formatear_fecha, parsear_fecha_usuario


class TestFormatearFecha:
    def test_writes_day_month_year(self) -> None:
        assert formatear_fecha(dt.date(2022, 9, 21)) == "21/09/2022"

    def test_never_contains_a_hour(self) -> None:
        texto = formatear_fecha(dt.datetime(2023, 4, 4, 15, 37, 12))
        assert texto == "04/04/2023"
        assert ":" not in texto

    def test_discards_the_time_of_a_datetime(self) -> None:
        assert formatear_fecha(dt.datetime(2023, 4, 4, 23, 59, 59)) == "04/04/2023"

    def test_empty_date_shows_nothing(self) -> None:
        # 2 rows have no dates at all and 135 are still in the workshop.
        assert formatear_fecha(None) == ""


class TestParsearFechaUsuario:
    def test_accepts_the_expected_format(self) -> None:
        assert parsear_fecha_usuario("21/09/2022") == dt.date(2022, 9, 21)

    def test_zero_padding_is_optional_for_fast_typing(self) -> None:
        assert parsear_fecha_usuario("7/2/2024") == dt.date(2024, 2, 7)

    def test_surrounding_space_is_ignored(self) -> None:
        assert parsear_fecha_usuario("  21/09/2022 ") == dt.date(2022, 9, 21)

    @pytest.mark.parametrize(
        "entrada",
        ["21/09/2022 12:00:00", "2022-09-21", "21/09", "no es fecha", ""],
    )
    def test_rejects_hours_and_other_formats(self, entrada: str) -> None:
        with pytest.raises(ValueError, match="dd/mm/aaaa"):
            parsear_fecha_usuario(entrada)

    def test_round_trip_survives_formatting(self) -> None:
        original = dt.date(2026, 10, 29)
        assert parsear_fecha_usuario(formatear_fecha(original)) == original
