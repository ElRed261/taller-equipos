"""Export the movements to CSV.

Decisions that matter for the people who will open this in Excel:

* **``;`` as delimiter and UTF-8 with BOM.** Excel in a Spanish locale splits on
  the semicolon, and without the BOM it renders ``Diagnóstico`` as
  ``DiagnÃ³stico``. A comma-delimited UTF-8 file looks correct in a code editor
  and broken in the program the institution actually uses.
* **``dd/mm/aaaa`` dates, never a time.** Same rule as the interface: the source
  data has no time of day, so exporting one would invent it.
* **The export is what you see.** Rows come from the filtered, sorted view, so a
  technician who searched "Contabilidad" gets Contabilidad and nothing else.

The formatting functions are pure: no file, no widget, no database.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from pathlib import Path

from taller.schemas.movimiento import MovimientoLeido
from taller.ui.tema import ETIQUETA_ESTADO

DELIMITADOR = ";"
FIN_DE_LINEA = "\r\n"
CODIFICACION = "utf-8-sig"

ENCABEZADOS = (
    "Estado",
    "Fecha de entrada",
    "Fecha de salida",
    "Área",
    "Equipo",
    "Modelo",
    "Inventario",
    "Service Tag",
    "Soportes",
    "Diagnóstico",
    "Nota",
    "Requiere revisión",
)


def fila_a_columnas(fila: MovimientoLeido) -> list[str]:
    """One movement as the values of one CSV line."""
    return [
        ETIQUETA_ESTADO[fila.estado],
        fila.fecha_entrada_texto,
        fila.fecha_salida_texto,
        fila.area or "",
        fila.tipo_equipo or "",
        fila.modelo or "",
        fila.codigo_inventario or "",
        fila.service_tag or "",
        ", ".join(fila.soporte),
        fila.diagnostico or "",
        fila.nota or "",
        "Sí" if fila.requiere_revision else "No",
    ]


def filas_a_csv(filas: Iterable[MovimientoLeido]) -> str:
    """Render the rows as CSV text, without the BOM (the file writer adds it)."""
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=DELIMITADOR, lineterminator=FIN_DE_LINEA)
    escritor.writerow(ENCABEZADOS)
    for fila in filas:
        escritor.writerow(fila_a_columnas(fila))
    return salida.getvalue()


def escribir_csv(ruta: Path, filas: Sequence[MovimientoLeido]) -> int:
    """Write the file and return how many data rows were written.

    ``utf-8-sig`` adds the BOM that Excel needs to read the accents correctly.
    """
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(filas_a_csv(filas), encoding=CODIFICACION, newline="")
    return len(filas)


def nombre_sugerido(fecha_hora: str) -> str:
    """``movimientos-AAAAMMDD-HHMM.csv``, from an ISO-ish timestamp string."""
    limpio = fecha_hora.replace("-", "").replace(":", "").replace(" ", "-")[:13]
    return f"movimientos-{limpio}.csv"
