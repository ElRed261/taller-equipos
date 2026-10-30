"""Parsing and cleaning rules for the legacy CSV export.

The source file was produced by exporting a .NET WinForms ``DataGridView`` to
text. Its first column serialises ``System.Drawing.Bitmap`` (the cell icon) and
carries no information, every time component is ``12:00:00 a. m.``, and the
free-text columns are full of typing variants.

Everything in this module is pure: no database, no I/O beyond the string it is
given. That is what makes the migration rules testable and re-runnable.

Policy: correct only what has one deterministic correction; never invent a value
for a field the source left empty; preserve provenance for every change.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from dataclasses import dataclass, field
from typing import Final

from taller.inventario import MARCADORES_SIN_CODIGO, normalizar_codigo
from taller.texto import clave_alias, normalizar_espacios

ORIGEN: Final = "csv_v1"

#: Column order of the legacy export, including the icon column we discard.
COLUMNAS: Final = (
    "Estado",
    "FechaEntrada",
    "Equipo",
    "Área",
    "Modelo",
    "Inventario",
    "Diagnóstico",
    "FechaSalida",
    "ServiceTag",
    "Soporte",
    "Nota",
)

#: A row whose year predates this is a typo for the same day in a later century.
ANIO_MINIMO_PLAUSIBLE: Final = 1990

#: A repaired date may not land further than this after the intake date before
#: we stop calling it a typo and start calling it an unexplained inversion.
MAX_DIAS_CORRECCION: Final = 30

#: Neighbour-bounded inference only fires when the window is this tight.
MAX_DIAS_INFERENCIA: Final = 7

_SEPARADOR_TECNICOS: Final = re.compile(r"\s*(?:&|,|/|\+| y )\s*", re.IGNORECASE)
# Re-exported: the ETL's public surface keeps naming this ``normalizar_texto``,
# and both names must mean exactly what the search proxy means by them.
normalizar_texto = normalizar_espacios
_FECHA: Final = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([ap])\.\s*m\.$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FilaLegacy:
    """One cleaned row, ready to become a ``movimiento``."""

    linea: int
    fecha_entrada: dt.date | None
    fecha_salida: dt.date | None
    fecha_entrada_inferida: bool = False
    requiere_revision: bool = False
    motivos: tuple[str, ...] = field(default_factory=tuple)
    equipo: str | None = None
    area: str | None = None
    modelo: str | None = None
    codigo_inventario: str | None = None
    service_tag: str | None = None
    diagnostico: str | None = None
    nota: str | None = None
    soporte: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        assert self.linea >= 2, "line numbers are 1-based file lines; row 1 is the header"
        if (
            self.fecha_entrada is not None
            and self.fecha_salida is not None
            and self.fecha_salida < self.fecha_entrada
            and not self.requiere_revision
        ):
            raise ValueError(f"line {self.linea}: inverted dates must be flagged for review")


# Re-exported: the ETL's public surface keeps naming this ``normalizar_texto``,
# and both names must mean exactly what the search proxy means by them.
normalizar_texto = normalizar_espacios

def parsear_fecha(valor: str | None) -> dt.date | None:
    """Parse ``d/M/yyyy h:mm:ss a. m.`` and keep only the date.

    All 1136 dates in the source are midnight, so the time component carries no
    information; keeping it would imply a precision the data does not have.
    """
    limpio = normalizar_texto(valor)
    if limpio is None:
        return None
    coincidencia = _FECHA.match(limpio)
    if coincidencia is None:
        raise ValueError(f"unparseable date: {valor!r}")
    dia, mes, anio, _h, _m, _s, _meridiano = coincidencia.groups()
    return dt.date(int(anio), int(mes), int(dia))


def limpiar_codigo_inventario(valor: str | None) -> str | None:
    """Delegate to the single normalisation rule in ``taller.inventario``."""
    return normalizar_codigo(valor)


def separar_tecnicos(valor: str | None) -> tuple[str, ...]:
    """Split a support cell into individual technicians.

    The source packs collaborators into one cell: ``Alejandro & Guillen``,
    ``Guillen & Yohanna``. Order is preserved and duplicates collapse.

    Explicit "no value" markers are checked *before* splitting: ``N/A`` would
    otherwise split on the slash and invent technicians called ``N`` and ``A``.
    """
    limpio = normalizar_texto(valor)
    if limpio is None or clave_alias(limpio) in MARCADORES_SIN_CODIGO:
        return ()
    partes = [normalizar_texto(p) for p in _SEPARADOR_TECNICOS.split(limpio)]
    vistos: dict[str, str] = {}
    for parte in partes:
        if parte is None:
            continue
        vistos.setdefault(clave_alias(parte), parte)
    return tuple(vistos.values())


def _reparar_anio(anio: int) -> int | None:
    """Map an implausible year (``1023``) to its likely century (``2023``)."""
    if anio >= ANIO_MINIMO_PLAUSIBLE:
        return anio
    candidato = anio + 1000
    if 2000 <= candidato <= 2100:
        return candidato
    return None


def corregir_fechas(
    entrada: dt.date | None,
    salida: dt.date | None,
    *,
    vecina_anterior: dt.date | None = None,
    vecina_posterior: dt.date | None = None,
) -> tuple[dt.date | None, dt.date | None, bool, bool, tuple[str, ...]]:
    """Apply the documented correction rules to one row.

    Returns ``(entrada, salida, entrada_inferida, requiere_revision, motivos)``.

    Rules, in order:
    1. An implausible year (before 1990) is shifted one century when that lands
       in 2000-2100.
    2. A departure earlier than the intake whose year alone explains the gap is
       a typo: the year is replaced when the repaired date falls within
       ``MAX_DIAS_CORRECCION`` after the intake.
    3. A missing intake is inferred only when its neighbours bound it inside
       ``MAX_DIAS_INFERENCIA`` days.
    4. Anything else is imported as-is and flagged, never guessed.
    """
    motivos: list[str] = []
    inferida = False

    if entrada is not None:
        anio = _reparar_anio(entrada.year)
        if anio is not None and anio != entrada.year:
            motivos.append(f"anio_entrada_corregido:{entrada.year}->{anio}")
            entrada = entrada.replace(year=anio)

    if salida is not None:
        anio = _reparar_anio(salida.year)
        if anio is not None and anio != salida.year:
            motivos.append(f"anio_salida_corregido:{salida.year}->{anio}")
            salida = salida.replace(year=anio)

    if entrada is not None and salida is not None and salida < entrada:
        reparada = _reparar_por_anio(entrada, salida)
        if reparada is not None:
            motivos.append(f"salida_reparada:{salida.isoformat()}->{reparada.isoformat()}")
            salida = reparada
        else:
            motivos.append("salida_anterior_a_entrada_sin_correccion_unica")
            return entrada, salida, inferida, True, tuple(motivos)

    if entrada is None:
        # Neighbour bounds can close a missing intake date even when the row has
        # no dispatch date yet: the ticket is still open, but it did come in
        # between those two recorded intakes.
        limite_inferior = vecina_anterior
        cotas_superiores = [d for d in (salida, vecina_posterior) if d is not None]
        limite_superior = min(cotas_superiores) if cotas_superiores else None

        if (
            limite_inferior is not None
            and limite_superior is not None
            and limite_superior >= limite_inferior
            and (limite_superior - limite_inferior).days <= MAX_DIAS_INFERENCIA
        ):
            motivos.append(
                f"entrada_inferida:{limite_inferior.isoformat()}<x<={limite_superior.isoformat()}"
            )
            return limite_superior, salida, True, False, tuple(motivos)

        motivos.append("sin_fechas" if salida is None else "sin_fecha_entrada")
        return None, salida, inferida, True, tuple(motivos)

    return entrada, salida, inferida, False, tuple(motivos)


def _reparar_por_anio(entrada: dt.date, salida: dt.date) -> dt.date | None:
    """Return ``salida`` with a plausible year, or ``None`` when no year fits."""
    for anio in (entrada.year, entrada.year + 1):
        try:
            candidata = salida.replace(year=anio)
        except ValueError:  # 29 February in a non-leap year
            continue
        if 0 <= (candidata - entrada).days <= MAX_DIAS_CORRECCION:
            return candidata
    return None


def sha256_archivo(contenido: bytes) -> str:
    return hashlib.sha256(contenido).hexdigest()


def parsear_csv(texto: str) -> list[FilaLegacy]:
    """Parse the whole export, applying correction rules with neighbour context.

    A leading byte-order mark is tolerated here rather than at the call site:
    the file is UTF-8 with BOM, and decoding it as plain ``utf-8`` silently
    renames the first column to ``\ufeffEstado``.
    """
    import csv
    import io

    if texto.startswith("\ufeff"):
        texto = texto[1:]

    lector = csv.DictReader(io.StringIO(texto), delimiter=";")
    if lector.fieldnames is None:
        raise ValueError("empty file")
    faltantes = [c for c in COLUMNAS if c not in lector.fieldnames]
    if faltantes:
        raise ValueError(f"missing columns: {faltantes}")

    crudas: list[dict[str, str]] = [
        fila for fila in lector if any(valor and valor.strip() for valor in fila.values())
    ]
    entradas_crudas = [parsear_fecha(f.get("FechaEntrada")) for f in crudas]

    filas: list[FilaLegacy] = []
    for indice, (fila, entrada) in enumerate(zip(crudas, entradas_crudas, strict=True)):
        salida = parsear_fecha(fila.get("FechaSalida"))
        anterior = next((e for e in reversed(entradas_crudas[:indice]) if e is not None), None)
        posterior = next((e for e in entradas_crudas[indice + 1 :] if e is not None), None)

        entrada_final, salida_final, inferida, revision, motivos = corregir_fechas(
            entrada,
            salida,
            vecina_anterior=anterior,
            vecina_posterior=posterior,
        )

        filas.append(
            FilaLegacy(
                linea=indice + 2,  # 1-based file line, row 1 is the header
                fecha_entrada=entrada_final,
                fecha_salida=salida_final,
                fecha_entrada_inferida=inferida,
                requiere_revision=revision,
                motivos=motivos,
                equipo=normalizar_texto(fila.get("Equipo")),
                area=normalizar_texto(fila.get("Área")),
                modelo=normalizar_texto(fila.get("Modelo")),
                codigo_inventario=limpiar_codigo_inventario(fila.get("Inventario")),
                service_tag=normalizar_texto(fila.get("ServiceTag")),
                diagnostico=normalizar_texto(fila.get("Diagnóstico")),
                nota=normalizar_texto(fila.get("Nota")),
                soporte=separar_tecnicos(fila.get("Soporte")),
            )
        )
    return filas


def canonizar(valores: list[str | None]) -> dict[str, str]:
    """Map every alias key to its most frequent spelling.

    Returns ``{clave_alias: forma_canonica}``. Ties break on the alphabetically
    first spelling so the result is deterministic across runs.
    """
    conteo: dict[str, dict[str, int]] = {}
    for valor in valores:
        if valor is None:
            continue
        conteo.setdefault(clave_alias(valor), {}).setdefault(valor, 0)
        conteo[clave_alias(valor)][valor] += 1

    canonico: dict[str, str] = {}
    for clave, variantes in conteo.items():
        canonico[clave] = sorted(variantes.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return canonico
