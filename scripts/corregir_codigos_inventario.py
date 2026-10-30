#!/usr/bin/env python3
"""Apply the inventory-code rule to the rows already in the database.

The rule lives in ``taller.inventario``; this script is the one-off pass that
brings existing data in line with it, and it leaves a trail: every changed row
gets an ``auditoria_edicion`` entry with the old and the new value, so nobody has
to trust that the codes were rewritten correctly.

    scripts/corregir_codigos_inventario.py
    scripts/corregir_codigos_inventario.py --aplicar
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import select  # noqa: E402

from taller.database.connection import session_scope  # noqa: E402
from taller.database.models import AuditoriaEdicion, Movimiento, Usuario  # noqa: E402
from taller.inventario import normalizar_codigo  # noqa: E402

ETIQUETA = "migracion:codigos-inventario"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normaliza los códigos de inventario.")
    parser.add_argument("--aplicar", action="store_true", help="Escribe los cambios.")
    args = parser.parse_args(argv)

    with session_scope() as sesion:
        movimientos = sesion.scalars(
            select(Movimiento).where(Movimiento.codigo_inventario.is_not(None))
        ).all()

        cambios: list[tuple[Movimiento, str | None]] = []
        for movimiento in movimientos:
            nuevo = normalizar_codigo(movimiento.codigo_inventario)
            if nuevo != movimiento.codigo_inventario:
                cambios.append((movimiento, nuevo))

        print(f"movimientos con código: {len(movimientos)}")
        print(f"códigos a corregir: {len(cambios)}\n")
        for movimiento, nuevo in cambios:
            print(
                f"  línea {movimiento.legacy_linea:>4}: "
                f"{movimiento.codigo_inventario!r} -> {nuevo!r}"
            )

        if not cambios:
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

        for movimiento, nuevo in cambios:
            sesion.add(
                AuditoriaEdicion(
                    movimiento_id=movimiento.id,
                    campo="codigo_inventario",
                    valor_anterior=movimiento.codigo_inventario,
                    valor_nuevo=nuevo,
                    usuario_id=autor.id,
                    usuario_etiqueta=ETIQUETA,
                )
            )
            movimiento.codigo_inventario = nuevo
        sesion.flush()
        print(f"\n{len(cambios)} códigos corregidos y auditados.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
