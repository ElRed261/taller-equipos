"""Schemas for reading and writing movements.

Three shapes, and the difference between them is the whole point:

* ``MovimientoCrear``   — what the form sends. Nothing derived, nothing imported.
* ``MovimientoActualizar`` — a partial edit. Absent fields mean "leave it"; an
  explicit ``None`` means "clear it", which is why the repository must use
  ``model_dump(exclude_unset=True)``.
* ``MovimientoLeido``   — what the grid renders. Flat, with catalog names already
  resolved and a precomputed search key, so the table model never touches the
  database.

Validation lives here rather than in the widgets: a rule that only exists in a
Qt delegate does not protect the data when someone edits from psql.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from taller.formato import formatear_fecha
from taller.inventario import normalizar_codigo
from taller.texto import clave_alias, normalizar_espacios

Estado = Literal["en_taller", "despachado", "sin_datos"]


class FechasInvalidas(ValueError):
    """Raised when a departure date would precede the intake date."""


def validar_orden_fechas(entrada: dt.date | None, salida: dt.date | None) -> None:
    """Enforce the same rule as ``ck_movimiento_fechas``, with a usable message.

    The database still holds the last line of defence; this exists so the grid
    can show ``la fecha de salida (05/01/2024) no puede ser anterior a la fecha
    de entrada (10/01/2024)`` instead of a constraint name.
    """
    if entrada is None or salida is None or salida >= entrada:
        return
    raise FechasInvalidas(
        f"la fecha de salida ({formatear_fecha(salida)}) no puede ser anterior "
        f"a la fecha de entrada ({formatear_fecha(entrada)})"
    )


class _CamposEditables(BaseModel):
    """Fields a technician may change. Derived and provenance fields are absent."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    fecha_entrada: dt.date | None = None
    fecha_salida: dt.date | None = None
    tipo_equipo_id: int | None = None
    area_id: int | None = None
    modelo: str | None = None
    codigo_inventario: str | None = None
    service_tag: str | None = None
    diagnostico: str | None = None
    nota: str | None = None

    @field_validator("modelo", "service_tag", "diagnostico", "nota", mode="before")
    @classmethod
    def _limpiar_texto(cls, valor: object) -> str | None:
        if not isinstance(valor, str):
            return None if valor is None else str(valor)
        return normalizar_espacios(valor)

    @field_validator("codigo_inventario", mode="before")
    @classmethod
    def _limpiar_inventario(cls, valor: object) -> str | None:
        """Normalise the code with the single shared rule.

        The institution confirmed on 2026-10-30 that ``O2071`` really is ``02071``,
        so converting a leading O to a zero is a documented rule, not a guess. And
        a code typed with a leading zero keeps it: that is why the column is text.
        """
        if valor is None:
            return None
        return normalizar_codigo(valor if isinstance(valor, str) else str(valor))


class MovimientoCrear(_CamposEditables):
    """A new movement. ``requiere_revision`` and ``origen`` are not settable.

    Date order is **not** validated here on purpose: a ``model_validator`` that
    raises would be wrapped by Pydantic into a ``ValidationError``, and the UI
    could no longer distinguish "la salida es anterior a la entrada" from "eso
    no es un entero". The rule lives in ``validar_orden_fechas``, which the
    repository calls before writing, so one exception type reaches the caller.
    """

    tecnicos: list[int] = Field(default_factory=list)


class MovimientoActualizar(_CamposEditables):
    """A partial edit: only the fields present in the payload are applied."""

    tecnicos: list[int] | None = None


class MovimientoLeido(BaseModel):
    """One row as the grid needs it: flat, resolved and search-ready."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    fecha_entrada: dt.date | None = None
    fecha_salida: dt.date | None = None
    estado: Estado
    area_id: int | None = None
    tipo_equipo_id: int | None = None
    tipo_equipo: str | None = None
    area: str | None = None
    modelo: str | None = None
    codigo_inventario: str | None = None
    service_tag: str | None = None
    diagnostico: str | None = None
    nota: str | None = None
    soporte: list[str] = Field(default_factory=list)
    requiere_revision: bool = False
    fecha_entrada_inferida: bool = False
    legacy_linea: int | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def texto_busqueda(self) -> str:
        """Accent- and case-insensitive haystack the search proxy matches against."""
        partes = [
            self.codigo_inventario,
            self.service_tag,
            self.modelo,
            self.diagnostico,
            self.nota,
            self.area,
            self.tipo_equipo,
            " ".join(self.soporte),
        ]
        return clave_alias(" ".join(parte for parte in partes if parte))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fecha_entrada_texto(self) -> str:
        return formatear_fecha(self.fecha_entrada)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fecha_salida_texto(self) -> str:
        return formatear_fecha(self.fecha_salida)


class CatalogoLeido(BaseModel):
    """A catalog row (area, technician or equipment type)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    activo: bool = True


class CatalogoConUso(CatalogoLeido):
    """A catalog row plus how many movements depend on it.

    The count is what makes a merge safe to offer: it tells the user how much
    history is about to change hands, and it lets the app pick the row with more
    history as the one that survives.
    """

    movimientos: int = 0


class ResumenEstados(BaseModel):
    """Counts for the status filter chips above the grid."""

    en_taller: int = 0
    despachado: int = 0
    sin_datos: int = 0
    pendientes_revision: int = 0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total(self) -> int:
        return self.en_taller + self.despachado + self.sin_datos
