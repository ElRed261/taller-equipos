#!/usr/bin/env python3
"""Comprueba que dos puestos comparten los datos.

Simula dos PC del taller: cada una abre su propio servicio, con su propia conexión
y su propio usuario. Lo que uno registra lo ve el otro, y la auditoría dice quién
hizo cada cosa.

Crea un registro de prueba y lo borra al final; no toca los datos reales.

    scripts/verificar_multiusuario.py
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from sqlalchemy import delete, select  # noqa: E402

from taller.database.connection import session_scope  # noqa: E402
from taller.database.models import (  # noqa: E402
    AuditoriaEdicion,
    Movimiento,
    MovimientoTecnico,
)
from taller.schemas.movimiento import MovimientoActualizar, MovimientoCrear  # noqa: E402
from taller.servicios import ServicioTaller  # noqa: E402

MARCA = "__prueba_multiusuario__"


def main() -> int:
    puesto_uno = ServicioTaller("puesto-uno")
    puesto_dos = ServicioTaller("puesto-dos")
    ok, detalle = puesto_uno.conexion_ok()
    print(f"conexión: {detalle}")
    if not ok:
        return 1

    creado = None
    fallos: list[str] = []
    try:
        creado = puesto_uno.crear_movimiento(
            MovimientoCrear(
                fecha_entrada=dt.date.today(),
                modelo=MARCA,
                diagnostico="registrado desde el puesto uno",
            )
        )
        print(f"1. el puesto uno registró el movimiento {creado.id}")

        visto = [f for f in puesto_dos.listar_movimientos() if f.id == creado.id]
        if not visto:
            fallos.append("el puesto dos no ve el registro del puesto uno")
        else:
            print(f"2. el puesto dos lo ve: «{visto[0].modelo}» · {visto[0].estado}")

        puesto_dos.actualizar(
            creado.id, MovimientoActualizar(nota="editado desde el puesto dos")
        )
        releido = puesto_uno.obtener(creado.id)
        if releido.nota != "editado desde el puesto dos":
            fallos.append("el puesto uno no ve la edición del puesto dos")
        else:
            print(f"3. el puesto uno ve la edición del puesto dos: «{releido.nota}»")

        historial = puesto_uno.historial(creado.id)
        autores = {entrada["usuario"] for entrada in historial}
        if "puesto-dos" not in autores:
            fallos.append("la auditoría no atribuye la edición al puesto dos")
        else:
            print(f"4. auditoría: {autores}")

        despachado = puesto_uno.marcar_salida(creado.id, dt.date.today())
        if puesto_dos.obtener(creado.id).estado != "despachado":
            fallos.append("el puesto dos no ve la salida registrada por el uno")
        else:
            print(
                f"5. el puesto dos ve la salida del mismo día: {despachado.fecha_salida_texto}"
            )
    finally:
        # La auditoría y los vínculos apuntan al movimiento con ON DELETE RESTRICT:
        # hay que borrarlos antes, en ese orden.
        with session_scope() as sesion:
            ids = list(
                sesion.scalars(select(Movimiento.id).where(Movimiento.modelo == MARCA))
            )
            if creado is not None:
                ids.append(creado.id)
            for movimiento_id in set(ids):
                sesion.execute(
                    delete(AuditoriaEdicion).where(
                        AuditoriaEdicion.movimiento_id == movimiento_id
                    )
                )
                sesion.execute(
                    delete(MovimientoTecnico).where(
                        MovimientoTecnico.movimiento_id == movimiento_id
                    )
                )
                fila = sesion.get(Movimiento, movimiento_id)
                if fila is not None:
                    sesion.delete(fila)

    print()
    if fallos:
        for fallo in fallos:
            print(f"FALLO: {fallo}", file=sys.stderr)
        return 1
    print("OK: dos puestos comparten registros, ediciones, salidas y auditoría.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
