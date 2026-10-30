"""Writes parsed legacy rows into the database.

The import is idempotent twice over: the SHA-256 of the source file is recorded
in ``importacion`` (so re-running the same file is refused unless forced), and
``movimiento`` carries a unique ``(origen, legacy_linea)`` pair (so a forced or
interrupted run only fills the gaps).

Alias resolution is not hardcoded inside the loop: every distinct dirty value is
resolved once through ``canonizar`` and recorded in ``mapeo_legacy``, which is
what makes the cleaning reviewable later.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from taller.database.models import (
    Area,
    Importacion,
    MapeoLegacy,
    Movimiento,
    MovimientoTecnico,
    Tecnico,
    TipoEquipo,
)
from taller.etl.legacy_csv import (
    MARCADORES_SIN_CODIGO,
    ORIGEN,
    FilaLegacy,
    canonizar,
    clave_alias,
)


class ImportacionRechazada(RuntimeError):
    """Raised when a run would duplicate an already imported source file."""


@dataclass
class Reporte:
    archivo: str
    sha256: str
    filas_leidas: int = 0
    filas_insertadas: int = 0
    filas_omitidas: int = 0
    filas_con_revision: int = 0
    filas_con_entrada_inferida: int = 0
    filas_rechazadas: int = 0
    areas: int = 0
    tecnicos: int = 0
    tipos_equipo: int = 0
    alias_areas: int = 0
    alias_tecnicos: int = 0
    motivos: Counter[str] = field(default_factory=Counter)
    inventarios_sospechosos: list[str] = field(default_factory=list)
    posibles_duplicados_tecnico: list[tuple[str, str]] = field(default_factory=list)
    seco: bool = False

    def resumen(self) -> str:
        lineas = [
            f"{'[SECO] ' if self.seco else ''}Archivo: {self.archivo}",
            f"SHA-256: {self.sha256}",
            "",
            f"Filas leídas        : {self.filas_leidas}",
            f"Filas insertadas    : {self.filas_insertadas}",
            f"Filas ya presentes  : {self.filas_omitidas}",
            f"Filas para revisar  : {self.filas_con_revision}",
            f"Entradas inferidas  : {self.filas_con_entrada_inferida}",
            f"Filas rechazadas    : {self.filas_rechazadas}",
            "",
            f"Áreas creadas       : {self.areas} (alias resueltos: {self.alias_areas})",
            f"Técnicos creados    : {self.tecnicos} (alias resueltos: {self.alias_tecnicos})",
            f"Tipos de equipo     : {self.tipos_equipo}",
        ]
        if self.motivos:
            lineas += ["", "Motivos de revisión:"]
            ordenados = sorted(self.motivos.items(), key=lambda kv: -kv[1])
            lineas += [f"  {motivo:<52} {total}" for motivo, total in ordenados]
        if self.inventarios_sospechosos:
            lineas += [
                "",
                "Códigos de inventario con 'O' mezclada con dígitos (no se reescribieron):",
                "  " + ", ".join(self.inventarios_sospechosos),
            ]
        if self.posibles_duplicados_tecnico:
            lineas += [
                "",
                "Posibles duplicados de técnico (decidir en la ventana de configuración):",
            ]
            lineas += [f"  {a!r} ~ {b!r}" for a, b in self.posibles_duplicados_tecnico]
        return "\n".join(lineas)


def _catalogo(
    session: Session,
    modelo: type[Any],
    valores: list[str],
    dimension: str,
    seco: bool,
) -> tuple[dict[str, int], int]:
    """Upsert catalog rows and record the alias map.

    Returns ``({clave_alias: id}, alias_nuevos)``.
    """
    canonico = canonizar(valores)
    existentes: dict[str, int] = {
        nombre: identificador
        for nombre, identificador in session.execute(select(modelo.nombre, modelo.id)).all()
    }

    ids: dict[str, int] = {}
    for clave, nombre in sorted(canonico.items()):
        if nombre not in existentes and not seco:
            objeto = modelo(nombre=nombre)
            session.add(objeto)
            session.flush()
            existentes[nombre] = objeto.id
        ids[clave] = existentes.get(nombre, 0)

    if seco:
        return ids, len(set(valores))

    alias_nuevos = 0
    ya_mapeados = set(
        session.scalars(
            select(MapeoLegacy.valor_origen).where(MapeoLegacy.dimension == dimension)
        ).all()
    )
    for valor in sorted(set(valores)):
        if valor in ya_mapeados:
            continue
        session.add(
            MapeoLegacy(
                dimension=dimension,
                valor_origen=valor,
                destino_id=ids[clave_alias(valor)],
            )
        )
        alias_nuevos += 1

    return ids, alias_nuevos


def importar(
    session: Session,
    filas: list[FilaLegacy],
    *,
    archivo: str,
    sha256: str,
    seco: bool = False,
    forzar: bool = False,
) -> Reporte:
    reporte = Reporte(archivo=archivo, sha256=sha256, filas_leidas=len(filas), seco=seco)

    previa = session.scalar(select(Importacion).where(Importacion.sha256 == sha256))
    if previa is not None and not forzar:
        raise ImportacionRechazada(
            f"este archivo ya fue importado el {previa.ejecutada_en:%Y-%m-%d %H:%M} "
            f"({previa.filas_insertadas} filas). Usá --forzar para completar lo que falte."
        )

    areas, alias_areas = _catalogo(
        session,
        Area,
        [f.area for f in filas if f.area is not None],
        "area",
        seco,
    )
    tecnicos, alias_tecnicos = _catalogo(
        session,
        Tecnico,
        [t for f in filas for t in f.soporte],
        "tecnico",
        seco,
    )
    tipos, _ = _catalogo(
        session,
        TipoEquipo,
        [
            f.equipo
            for f in filas
            if f.equipo is not None and clave_alias(f.equipo) not in MARCADORES_SIN_CODIGO
        ],
        "tipo_equipo",
        seco,
    )
    reporte.areas = len(areas)
    reporte.tecnicos = len(tecnicos)
    reporte.tipos_equipo = len(tipos)
    reporte.alias_areas = alias_areas
    reporte.alias_tecnicos = alias_tecnicos

    ya_importadas: set[int] = set(
        session.scalars(
            select(Movimiento.legacy_linea).where(Movimiento.origen == ORIGEN)
        ).all()
    )

    for fila in filas:
        if fila.linea in ya_importadas:
            reporte.filas_omitidas += 1
            continue

        area_id = areas.get(clave_alias(fila.area)) if fila.area else None
        tipo_id = (
            tipos.get(clave_alias(fila.equipo))
            if fila.equipo and clave_alias(fila.equipo) not in MARCADORES_SIN_CODIGO
            else None
        )

        if not seco:
            movimiento = Movimiento(
                fecha_entrada=fila.fecha_entrada,
                fecha_salida=fila.fecha_salida,
                tipo_equipo_id=tipo_id or None,
                area_id=area_id or None,
                modelo=fila.modelo,
                codigo_inventario=fila.codigo_inventario,
                service_tag=fila.service_tag,
                diagnostico=fila.diagnostico,
                nota=fila.nota,
                fecha_entrada_inferida=fila.fecha_entrada_inferida,
                requiere_revision=fila.requiere_revision,
                origen=ORIGEN,
                legacy_linea=fila.linea,
            )
            session.add(movimiento)
            session.flush()

            for posicion, nombre in enumerate(fila.soporte):
                tecnico_id = tecnicos.get(clave_alias(nombre))
                if tecnico_id:
                    session.add(
                        MovimientoTecnico(
                            movimiento_id=movimiento.id,
                            tecnico_id=tecnico_id,
                            principal=posicion == 0,
                        )
                    )

        reporte.filas_insertadas += 1
        if fila.requiere_revision:
            reporte.filas_con_revision += 1
        if fila.fecha_entrada_inferida:
            reporte.filas_con_entrada_inferida += 1
        for motivo in fila.motivos:
            reporte.motivos[motivo.split(":")[0]] += 1
        if (
            fila.codigo_inventario
            and "O" in fila.codigo_inventario
            and any(caracter.isdigit() for caracter in fila.codigo_inventario)
        ):
            reporte.inventarios_sospechosos.append(
                f"{fila.codigo_inventario} (línea {fila.linea})"
            )

    reporte.posibles_duplicados_tecnico = _duplicados_probables(list(tecnicos))

    if not seco:
        session.add(
            Importacion(
                archivo=archivo,
                sha256=sha256,
                filas_leidas=reporte.filas_leidas,
                filas_insertadas=reporte.filas_insertadas,
                filas_con_revision=reporte.filas_con_revision,
                filas_rechazadas=reporte.filas_rechazadas,
                notas=f"alias áreas={reporte.alias_areas} técnicos={reporte.alias_tecnicos}",
            )
        )
        session.commit()

    return reporte


def _duplicados_probables(claves: list[str]) -> list[tuple[str, str]]:
    """Pairs of technician keys that are probably the same person.

    The source spells the same technician many ways: ``Juan Guilen``,
    ``Juan Guiilen``, ``juan Gullen``, ``Juan E Guillem``. They are reported as
    candidates and never merged: deciding that two spellings are one identity is
    a human decision, not a normalisation rule.
    """
    from difflib import SequenceMatcher

    candidatas = sorted(clave for clave in claves if len(clave) >= 4)
    pares: list[tuple[str, str]] = []
    for indice, corta in enumerate(candidatas):
        for larga in candidatas[indice + 1 :]:
            if SequenceMatcher(None, corta, larga).ratio() >= 0.82:
                pares.append((corta, larga))
    return pares[:25]
