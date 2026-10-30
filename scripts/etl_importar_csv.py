#!/usr/bin/env python3
"""Import the legacy workshop CSV into the database.

Usage:
    uv run python scripts/etl_importar_csv.py --csv "/path/Datos de movimiento..csv" --dry-run
    uv run python scripts/etl_importar_csv.py --csv "/path/Datos de movimiento..csv"

Exit codes:
    0  import completed (or a dry run completed)
    1  the file was already imported, or it could not be parsed
    2  bad usage
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from taller.database.connection import session_scope
from taller.etl.importer import ImportacionRechazada, importar
from taller.etl.legacy_csv import parsear_csv, sha256_archivo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import the legacy workshop CSV into the normalized schema."
    )
    parser.add_argument(
        "--csv",
        default=os.environ.get("TALLER_CSV_LEGADO"),
        help="Path to the legacy export (default: $TALLER_CSV_LEGADO).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing anything to the database.",
    )
    parser.add_argument(
        "--forzar",
        action="store_true",
        help="Import even if this exact file was imported before (fills only missing rows).",
    )
    parser.add_argument(
        "--informe",
        help="Write the report to this path in addition to stdout.",
    )
    args = parser.parse_args(argv)

    if not args.csv:
        parser.error("missing --csv (or set TALLER_CSV_LEGADO)")

    ruta = Path(args.csv).expanduser()
    if not ruta.is_file():
        print(f"error: no existe el archivo {ruta}", file=sys.stderr)
        return 1

    contenido = ruta.read_bytes()
    huella = sha256_archivo(contenido)

    try:
        filas = parsear_csv(contenido.decode("utf-8-sig"))
    except ValueError as exc:
        print(f"error al interpretar el CSV: {exc}", file=sys.stderr)
        return 1

    try:
        with session_scope() as session:
            reporte = importar(
                session,
                filas,
                archivo=str(ruta),
                sha256=huella,
                seco=args.dry_run,
                forzar=args.forzar,
            )
    except ImportacionRechazada as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    texto = reporte.resumen()
    print(texto)
    if args.informe:
        destino = Path(args.informe).expanduser()
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto + "\n", encoding="utf-8")
        print(f"\nInforme escrito en {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
