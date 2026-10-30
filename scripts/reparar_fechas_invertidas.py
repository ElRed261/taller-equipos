#!/usr/bin/env python3
"""Fix movements whose departure date is earlier than the intake date.

The legacy export has eight rows where the two dates are swapped: the technician
typed the intake in the departure field and the departure in the intake field.
Swapping them is the only fix that keeps both dates: clamping the departure to the
intake date would invent a same-day repair and throw the real date away.

Same-day intake and departure is perfectly valid and is not touched — it is the
most common case in the data (266 rows).

    scripts/reparar_fechas_invertidas.py
    scripts/reparar_fechas_invertidas.py --aplicar
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from taller.database.connection import session_scope  # noqa: E402
from taller.database.models import AuditoriaEdicion, Movimiento, Usuario  # noqa: E402

ETIQUETA = "migracion:fechas-invertidas"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Intercambia fechas invertidas.")
    parser.add_argument("--aplicar", action="store_true", help="Escribe los cambios.")
    args = parser.parse_args(argv)

    with session_scope() as sesion:
        filas = sesion.scalars(
            select(Movimiento).where(
                Movimiento.fecha_entrada.is_not(None),
                Movimiento.fecha_salida.is_not(None),
                Movimiento.fecha_salida < Movimiento.fecha_entrada,
            )
        ).all()

        print(f"filas con fechas invertidas: {len(filas)}\n")
        for movimiento in filas:
            dias = (movimiento.fecha_entrada - movimiento.fecha_salida).days  # type: ignore[operator]
            print(
                f"  línea {movimiento.legacy_linea:>4}: "
                f"{movimiento.fecha_entrada} / {movimiento.fecha_salida} "
                f"({dias} días) -> {movimiento.fecha_salida} / {movimiento.fecha_entrada}"
            )

        if not filas:
            print("\nNada que corregir.")
            return 0

        if not args.aplicar:
            print("\nMODO INFORME: no se escribió nada. Repetí con --aplicar.")
            return 0

        autor = sesion.scalar(select(Usuario).where(Usuario.nombre == ETIQUETA))
        if autor is None:
            autor = Usuario(nombre=ETIQUETA)
            sesion.add(autor)
            sesion.flush()

        momento = dt.datetime.now(dt.UTC)
        for movimiento in filas:
            entrada, salida = movimiento.fecha_entrada, movimiento.fecha_salida
            for campo, anterior, nuevo in (
                ("fecha_entrada", entrada, salida),
                ("fecha_salida", salida, entrada),
            ):
                sesion.add(
                    AuditoriaEdicion(
                        movimiento_id=movimiento.id,
                        campo=campo,
                        valor_anterior=str(anterior),
                        valor_nuevo=str(nuevo),
                        usuario_id=autor.id,
                        usuario_etiqueta=ETIQUETA,
                    )
                )
            movimiento.fecha_entrada = salida
            movimiento.fecha_salida = entrada
            # Ya no hay nada que revisar en esa fila: las fechas cierran.
            movimiento.requiere_revision = False
            movimiento.revisado_en = momento

        sesion.flush()

        restantes = sesion.scalar(
            select(Movimiento.id).where(
                Movimiento.fecha_salida.is_not(None),
                Movimiento.fecha_entrada.is_not(None),
                Movimiento.fecha_salida < Movimiento.fecha_entrada,
            )
        )
        print(f"\n{len(filas)} filas corregidas y auditadas.")
        print(f"quedan invertidas: {'ninguna' if restantes is None else restantes}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
