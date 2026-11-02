"""Repositories: the only place that builds queries.

Two rules this module keeps, both of which exist because Qt will call it:

* **Repositories never commit.** The caller owns the transaction through
  ``session_scope()``. A repository that commits on its own cannot be composed
  and cannot be rolled back in a test.
* **Repositories return Pydantic DTOs, never ORM instances.** A detached ORM
  object crossing a thread boundary is a ``DetachedInstanceError`` waiting for
  the first lazy load, and Qt signals cross threads routinely.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import delete, func, nulls_last, or_, select, update
from sqlalchemy.orm import Session

from taller.database.models import (
    ORIGEN_APP,
    Area,
    AuditoriaCatalogo,
    AuditoriaEdicion,
    Movimiento,
    MovimientoEliminado,
    MovimientoEstado,
    MovimientoTecnico,
    Tecnico,
    TipoEquipo,
    Usuario,
)
from taller.schemas.movimiento import (
    CatalogoLeido,
    Estado,
    FechasInvalidas,
    MovimientoActualizar,
    MovimientoCrear,
    MovimientoLeido,
    ResumenEstados,
    validar_orden_fechas,
)
from taller.schemas.usuario import UsuarioLeido
from taller.seguridad import clave_aceptable, hashear, necesita_rehash, verificar

ModeloCatalogo = TypeVar("ModeloCatalogo", Area, Tecnico, TipoEquipo)

#: Columns whose changes are written to ``auditoria_edicion``.
CAMPOS_AUDITABLES: tuple[str, ...] = (
    "fecha_entrada",
    "fecha_salida",
    "tipo_equipo_id",
    "area_id",
    "modelo",
    "codigo_inventario",
    "service_tag",
    "diagnostico",
    "nota",
)


#: Una fila «necesita atención» cuando está marcada para revisión o le falta algo
#: con lo que se pueda trabajar: la fecha (no se sabe si está adentro o afuera), el
#: área (no se sabe dónde está) o el código de inventario (no se puede encontrar).
#:
#: El tipo de equipo no cuenta: viene vacío en 403 de los 568 registros importados
#: del sistema viejo, y mandar el 71% de la lista al final la dejaría sin orden útil.
def necesita_atencion() -> Any:
    return or_(
        MovimientoEstado.requiere_revision.is_(True),
        MovimientoEstado.fecha_entrada.is_(None),
        MovimientoEstado.area_id.is_(None),
        MovimientoEstado.codigo_inventario.is_(None),
    )


class MovimientoNoEncontrado(LookupError):
    """The requested movement does not exist (or was never imported)."""


class CatalogoNoEncontrado(LookupError):
    """The requested catalog row does not exist."""


class NombreDuplicado(ValueError):
    """A catalog name must be unique, active or not."""


def _texto(valor: Any) -> str | None:
    """Serialise a column value for the audit trail."""
    if valor is None:
        return None
    if isinstance(valor, dt.date | dt.datetime):
        return valor.isoformat()
    return str(valor)


class MovimientoRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    # ------------------------------------------------------------------ reads

    def listar(
        self,
        *,
        estado: Estado | None = None,
        area_id: int | None = None,
        solo_pendientes_revision: bool = False,
        limite: int | None = None,
    ) -> list[MovimientoLeido]:
        """Rows for the grid: lo que hay que atender, al final.

        Primero lo que está en orden, con lo más nuevo arriba. Al final quedan las
        filas marcadas para revisión y las que tienen datos faltantes: son las que
        hay que resolver, y tenerlas separadas evita que se pierdan entre 568.
        """
        consulta = (
            select(MovimientoEstado, Area.nombre, TipoEquipo.nombre)
            .outerjoin(Area, Area.id == MovimientoEstado.area_id)
            .outerjoin(TipoEquipo, TipoEquipo.id == MovimientoEstado.tipo_equipo_id)
            .order_by(
                # Falso (en orden) primero, verdadero (necesita atención) al final:
                # el mismo orden que el índice, para que el plan lo pueda usar.
                necesita_atencion().asc(),
                nulls_last(MovimientoEstado.fecha_entrada.desc()),
                MovimientoEstado.id.desc(),
            )
        )
        if estado is not None:
            consulta = consulta.where(MovimientoEstado.estado == estado)
        if area_id is not None:
            consulta = consulta.where(MovimientoEstado.area_id == area_id)
        if solo_pendientes_revision:
            consulta = consulta.where(MovimientoEstado.requiere_revision.is_(True))
        if limite is not None:
            consulta = consulta.limit(limite)

        return self._armar(self._s.execute(consulta).all())

    def obtener(self, movimiento_id: int) -> MovimientoLeido:
        fila = self._s.execute(
            select(MovimientoEstado, Area.nombre, TipoEquipo.nombre)
            .outerjoin(Area, Area.id == MovimientoEstado.area_id)
            .outerjoin(TipoEquipo, TipoEquipo.id == MovimientoEstado.tipo_equipo_id)
            .where(MovimientoEstado.id == movimiento_id)
        ).first()
        if fila is None:
            raise MovimientoNoEncontrado(f"no existe el movimiento {movimiento_id}")
        return self._armar([fila])[0]

    def modelos_sugeridos(self, limite: int = 60) -> list[str]:
        """Most frequent model names, for the form's autocomplete.

        Taken from the data instead of a catalog: 285 spellings exist and nobody
        will curate them, but the frequent ones are the ones typed every day.
        """
        filas = self._s.execute(
            select(Movimiento.modelo, func.count())
            .where(Movimiento.modelo.is_not(None))
            .group_by(Movimiento.modelo)
            .order_by(func.count().desc(), Movimiento.modelo)
            .limit(limite)
        ).all()
        return [modelo for modelo, _ in filas if modelo]

    def resumen(self) -> ResumenEstados:
        conteo = dict(
            self._s.execute(
                select(MovimientoEstado.estado, func.count()).group_by(MovimientoEstado.estado)
            ).all()
        )
        pendientes = self._s.scalar(
            select(func.count()).select_from(Movimiento).where(Movimiento.requiere_revision.is_(True))
        )
        return ResumenEstados(
            en_taller=int(conteo.get("en_taller", 0)),
            despachado=int(conteo.get("despachado", 0)),
            sin_datos=int(conteo.get("sin_datos", 0)),
            pendientes_revision=int(pendientes or 0),
        )

    # ----------------------------------------------------------------- writes

    def crear(self, datos: MovimientoCrear, *, usuario: str) -> MovimientoLeido:
        validar_orden_fechas(datos.fecha_entrada, datos.fecha_salida)
        autor = self._usuario(usuario)
        movimiento = Movimiento(
            origen=ORIGEN_APP,
            creado_por_id=autor.id,
            fecha_entrada=datos.fecha_entrada,
            fecha_salida=datos.fecha_salida,
            tipo_equipo_id=datos.tipo_equipo_id,
            area_id=datos.area_id,
            modelo=datos.modelo,
            codigo_inventario=datos.codigo_inventario,
            service_tag=datos.service_tag,
            diagnostico=datos.diagnostico,
            nota=datos.nota,
        )
        self._s.add(movimiento)
        self._s.flush()
        self._reemplazar_tecnicos(movimiento.id, datos.tecnicos)
        self._s.flush()
        return self.obtener(movimiento.id)

    def actualizar(
        self,
        movimiento_id: int,
        cambios: MovimientoActualizar,
        *,
        usuario: str,
    ) -> MovimientoLeido:
        """Apply a partial edit, auditing every field that actually changed.

        ``requiere_revision`` is deliberately untouched here: fixing the data of
        a flagged row is a separate, explicit act (``marcar_revisado``).
        """
        movimiento = self._orm(movimiento_id)
        datos = cambios.model_dump(exclude_unset=True)

        tecnicos = datos.pop("tecnicos", None)
        entrada = datos.get("fecha_entrada", movimiento.fecha_entrada)
        salida = datos.get("fecha_salida", movimiento.fecha_salida)
        validar_orden_fechas(entrada, salida)

        autor = self._usuario(usuario)
        for campo, nuevo in datos.items():
            anterior = getattr(movimiento, campo)
            if anterior == nuevo:
                continue
            self._s.add(
                AuditoriaEdicion(
                    movimiento_id=movimiento.id,
                    campo=campo,
                    valor_anterior=_texto(anterior),
                    valor_nuevo=_texto(nuevo),
                    usuario_id=autor.id,
                    usuario_etiqueta=autor.nombre,
                )
            )
            setattr(movimiento, campo, nuevo)

        if tecnicos is not None:
            self._reemplazar_tecnicos(movimiento.id, tecnicos, autor=autor)

        self._s.flush()
        return self.obtener(movimiento.id)

    def marcar_revisado(self, movimiento_id: int, *, usuario: str) -> MovimientoLeido:
        """Clear the review flag once the row is consistent again.

        Clearing the flag removes the only escape hatch from
        ``ck_movimiento_fechas``, so the dates are validated first and the error
        message tells the technician which two dates clash.
        """
        movimiento = self._orm(movimiento_id)
        if not movimiento.requiere_revision:
            return self.obtener(movimiento_id)

        # "Revisado" significa que alguien confirmó los datos. Una fila sin fecha
        # de entrada no tiene nada que confirmar: validar_orden_fechas la dejaba
        # pasar vacía y la marca se podía sacar sin haber mirado nada.
        if movimiento.fecha_entrada is None:
            raise FechasInvalidas(
                "no se puede dar por revisado un registro sin fecha de entrada: "
                "cargá primero la fecha en que llegó el equipo"
            )

        validar_orden_fechas(movimiento.fecha_entrada, movimiento.fecha_salida)

        autor = self._usuario(usuario)
        self._s.add(
            AuditoriaEdicion(
                movimiento_id=movimiento.id,
                campo="requiere_revision",
                valor_anterior="true",
                valor_nuevo="false",
                usuario_id=autor.id,
                usuario_etiqueta=autor.nombre,
            )
        )
        movimiento.requiere_revision = False
        movimiento.revisado_en = dt.datetime.now(dt.UTC)
        self._s.flush()
        return self.obtener(movimiento.id)

    def eliminar(self, movimiento_id: int, *, usuario: str) -> None:
        """Delete a movement completely, leaving a snapshot behind.

        The links and the field-level audit rows point at the movement with
        ``ON DELETE RESTRICT``, so they have to go first. Before any of that, the
        whole record is copied into ``movimiento_eliminado``: after this method
        returns, that snapshot is the only place where the data still exists.
        """
        movimiento = self._orm(movimiento_id)
        autor = self._usuario(usuario)

        # Los nombres, no solo los ids: el catálogo puede renombrarse o borrarse
        # después, y entonces un snapshot con ids no diría nada.
        area = self._s.get(Area, movimiento.area_id) if movimiento.area_id else None
        tipo = (
            self._s.get(TipoEquipo, movimiento.tipo_equipo_id)
            if movimiento.tipo_equipo_id
            else None
        )

        snapshot = {
            "id": movimiento.id,
            "legacy_linea": movimiento.legacy_linea,
            "origen": movimiento.origen,
            "fecha_entrada": _texto(movimiento.fecha_entrada),
            "fecha_salida": _texto(movimiento.fecha_salida),
            "tipo_equipo_id": movimiento.tipo_equipo_id,
            "tipo_equipo": tipo.nombre if tipo else None,
            "area_id": movimiento.area_id,
            "area": area.nombre if area else None,
            "modelo": movimiento.modelo,
            "codigo_inventario": movimiento.codigo_inventario,
            "service_tag": movimiento.service_tag,
            "diagnostico": movimiento.diagnostico,
            "nota": movimiento.nota,
            "requiere_revision": movimiento.requiere_revision,
            "tecnicos": self._soportes([movimiento.id]).get(movimiento.id, []),
            "creado_en": _texto(movimiento.creado_en),
        }
        self._s.add(
            MovimientoEliminado(
                movimiento_id=movimiento.id,
                snapshot=json.dumps(snapshot, ensure_ascii=False, indent=2),
                usuario_etiqueta=autor.nombre,
            )
        )
        self._s.execute(
            delete(MovimientoTecnico).where(MovimientoTecnico.movimiento_id == movimiento.id)
        )
        self._s.execute(
            delete(AuditoriaEdicion).where(AuditoriaEdicion.movimiento_id == movimiento.id)
        )
        self._s.delete(movimiento)
        self._s.flush()

    def historial(self, movimiento_id: int) -> list[dict[str, Any]]:
        """Audit rows for one movement, newest first. Used by the detail panel."""
        filas = self._s.execute(
            select(AuditoriaEdicion)
            .where(AuditoriaEdicion.movimiento_id == movimiento_id)
            .order_by(AuditoriaEdicion.ocurrido_en.desc())
        ).scalars()
        return [
            {
                "campo": fila.campo,
                "valor_anterior": fila.valor_anterior,
                "valor_nuevo": fila.valor_nuevo,
                "usuario": fila.usuario_etiqueta,
                "ocurrido_en": fila.ocurrido_en,
            }
            for fila in filas
        ]

    # ---------------------------------------------------------------- helpers

    def _orm(self, movimiento_id: int) -> Movimiento:
        movimiento = self._s.get(Movimiento, movimiento_id)
        if movimiento is None:
            raise MovimientoNoEncontrado(f"no existe el movimiento {movimiento_id}")
        return movimiento

    def _usuario(self, nombre: str) -> Usuario:
        """Get or create the application user used for audit attribution."""
        limpio = nombre.strip()
        if not limpio:
            raise ValueError("hace falta un usuario para atribuir el cambio")
        autor = self._s.scalar(select(Usuario).where(Usuario.nombre == limpio))
        if autor is None:
            autor = Usuario(nombre=limpio)
            self._s.add(autor)
            self._s.flush()
        return autor

    def _reemplazar_tecnicos(
        self, movimiento_id: int, tecnicos: Sequence[int], *, autor: Usuario | None = None
    ) -> None:
        self._s.execute(
            delete(MovimientoTecnico).where(MovimientoTecnico.movimiento_id == movimiento_id)
        )
        for posicion, tecnico_id in enumerate(dict.fromkeys(tecnicos)):
            self._s.add(
                MovimientoTecnico(
                    movimiento_id=movimiento_id,
                    tecnico_id=tecnico_id,
                    principal=posicion == 0,
                )
            )

    def _soportes(self, ids: Sequence[int]) -> dict[int, list[str]]:
        if not ids:
            return {}
        filas = self._s.execute(
            select(MovimientoTecnico.movimiento_id, Tecnico.nombre)
            .join(Tecnico, Tecnico.id == MovimientoTecnico.tecnico_id)
            .where(MovimientoTecnico.movimiento_id.in_(ids))
            .order_by(MovimientoTecnico.principal.desc(), Tecnico.nombre)
        ).all()
        acumulado: dict[int, list[str]] = defaultdict(list)
        for movimiento_id, nombre in filas:
            acumulado[movimiento_id].append(nombre)
        return acumulado

    def _armar(self, filas: Sequence[Any]) -> list[MovimientoLeido]:
        ids = [fila[0].id for fila in filas]
        soportes = self._soportes(ids)
        return [
            MovimientoLeido(
                id=vista.id,
                fecha_entrada=vista.fecha_entrada,
                fecha_salida=vista.fecha_salida,
                estado=vista.estado,
                area_id=vista.area_id,
                tipo_equipo_id=vista.tipo_equipo_id,
                tipo_equipo=tipo,
                area=area,
                modelo=vista.modelo,
                codigo_inventario=vista.codigo_inventario,
                service_tag=vista.service_tag,
                diagnostico=vista.diagnostico,
                nota=vista.nota,
                soporte=soportes.get(vista.id, []),
                requiere_revision=vista.requiere_revision,
                fecha_entrada_inferida=vista.fecha_entrada_inferida,
                legacy_linea=vista.legacy_linea,
            )
            for vista, area, tipo in filas
        ]


class CatalogoRepository:
    """CRUD for the three master catalogs, including merging duplicates."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def listar(
        self, modelo: type[ModeloCatalogo], *, solo_activos: bool = True
    ) -> list[CatalogoLeido]:
        consulta = select(modelo).order_by(modelo.nombre)
        if solo_activos:
            consulta = consulta.where(modelo.activo.is_(True))
        return [
            CatalogoLeido.model_validate(fila, from_attributes=True)
            for fila in self._s.scalars(consulta)
        ]

    def listar_con_uso(
        self, modelo: type[ModeloCatalogo], *, solo_activos: bool = False
    ) -> list[tuple[CatalogoLeido, int]]:
        """Every catalog row with the number of movements that depend on it."""
        if modelo is Tecnico:
            conteo = (
                select(
                    MovimientoTecnico.tecnico_id.label("clave"),
                    func.count().label("total"),
                )
                .group_by(MovimientoTecnico.tecnico_id)
                .subquery()
            )
            consulta = (
                select(modelo, func.coalesce(conteo.c.total, 0))
                .outerjoin(conteo, conteo.c.clave == modelo.id)
                .order_by(func.coalesce(conteo.c.total, 0).desc(), modelo.nombre)
            )
        else:
            columna = Movimiento.area_id if modelo is Area else Movimiento.tipo_equipo_id
            conteo = (
                select(columna.label("clave"), func.count().label("total"))
                .where(columna.is_not(None))
                .group_by(columna)
                .subquery()
            )
            consulta = (
                select(modelo, func.coalesce(conteo.c.total, 0))
                .outerjoin(conteo, conteo.c.clave == modelo.id)
                .order_by(func.coalesce(conteo.c.total, 0).desc(), modelo.nombre)
            )
        if solo_activos:
            consulta = consulta.where(modelo.activo.is_(True))
        return [
            (CatalogoLeido.model_validate(fila, from_attributes=True), int(total))
            for fila, total in self._s.execute(consulta).all()
        ]

    def _anotar(
        self,
        modelo: type[ModeloCatalogo],
        registro_id: int,
        accion: str,
        campo: str,
        anterior: object,
        nuevo: object,
        *,
        usuario: str,
    ) -> None:
        """Write one catalog-audit row. Same shape as the movement audit trail."""
        limpio = usuario.strip()
        if not limpio:
            raise ValueError("hace falta un usuario para atribuir el cambio")
        autor = self._s.scalar(select(Usuario).where(Usuario.nombre == limpio))
        self._s.add(
            AuditoriaCatalogo(
                catalogo=_DIMENSIONES[modelo],
                registro_id=registro_id,
                accion=accion,
                campo=campo,
                valor_anterior=_texto(anterior),
                valor_nuevo=_texto(nuevo),
                usuario_id=autor.id if autor is not None else None,
                usuario_etiqueta=limpio,
            )
        )
        self._s.flush()

    def crear(
        self, modelo: type[ModeloCatalogo], nombre: str, *, usuario: str
    ) -> CatalogoLeido:
        limpio = nombre.strip()
        if not limpio:
            raise ValueError("el nombre no puede estar vacío")
        if self._s.scalar(select(modelo).where(modelo.nombre == limpio)) is not None:
            raise NombreDuplicado(f"ya existe «{limpio}»")
        fila = modelo(nombre=limpio)
        self._s.add(fila)
        self._s.flush()
        self._anotar(modelo, fila.id, "crear", "nombre", None, limpio, usuario=usuario)
        return CatalogoLeido.model_validate(fila, from_attributes=True)

    def renombrar(
        self, modelo: type[ModeloCatalogo], catalogo_id: int, nombre: str, *, usuario: str
    ) -> CatalogoLeido:
        fila = self._obtener(modelo, catalogo_id)
        limpio = nombre.strip()
        if not limpio:
            raise ValueError("el nombre no puede estar vacío")
        choque = self._s.scalar(
            select(modelo).where(modelo.nombre == limpio, modelo.id != catalogo_id)
        )
        if choque is not None:
            raise NombreDuplicado(f"ya existe «{limpio}»")
        anterior = fila.nombre
        fila.nombre = limpio
        self._s.flush()
        if anterior != limpio:
            self._anotar(
                modelo, catalogo_id, "renombrar", "nombre", anterior, limpio, usuario=usuario
            )
        return CatalogoLeido.model_validate(fila, from_attributes=True)

    def desactivar(
        self, modelo: type[ModeloCatalogo], catalogo_id: int, *, usuario: str
    ) -> None:
        """Logical delete: history keeps pointing at a row that still exists."""
        fila = self._obtener(modelo, catalogo_id)
        fila.activo = False
        self._s.flush()
        self._anotar(modelo, catalogo_id, "desactivar", "activo", True, False, usuario=usuario)

    def activar(
        self, modelo: type[ModeloCatalogo], catalogo_id: int, *, usuario: str
    ) -> None:
        """Undo a logical delete. Without this, deactivating is one-way."""
        fila = self._obtener(modelo, catalogo_id)
        fila.activo = True
        self._s.flush()
        self._anotar(modelo, catalogo_id, "activar", "activo", False, True, usuario=usuario)

    def fusionar(
        self,
        modelo: type[ModeloCatalogo],
        origen_id: int,
        destino_id: int,
        *,
        usuario: str,
    ) -> int:
        """Repoint every reference from ``origen`` to ``destino`` and deactivate it.

        Returns how many references moved. Merging is how the 190 area spellings
        and the 38 technician variants get untangled without losing history.
        """
        if origen_id == destino_id:
            raise ValueError("no se puede fusionar un registro consigo mismo")
        origen = self._obtener(modelo, origen_id)
        destino = self._obtener(modelo, destino_id)

        if modelo is Tecnico:
            movidos = self._fusionar_tecnico(origen_id, destino_id)
        elif modelo is Area:
            movidos = self._fusionar_columna(Movimiento.area_id, origen_id, destino_id)
        elif modelo is TipoEquipo:
            movidos = self._fusionar_columna(Movimiento.tipo_equipo_id, origen_id, destino_id)
        else:  # pragma: no cover - the type is closed by the TypeVar
            raise TypeError(f"catálogo no soportado: {modelo!r}")

        origen.activo = False
        self._s.flush()
        # Una fusión mueve historia: queda anotado a dónde fue, cuántas filas se
        # movieron y con qué nombre se llamaba antes cada uno.
        self._anotar(
            modelo,
            origen_id,
            "fusionar",
            "fusionado_en",
            f"{origen_id} · {origen.nombre}",
            f"{destino_id} · {destino.nombre}",
            usuario=usuario,
        )
        self._anotar(
            modelo, origen_id, "fusionar", "referencias_movidas", None, movidos, usuario=usuario
        )
        return movidos

    def _fusionar_columna(self, columna: Any, origen_id: int, destino_id: int) -> int:
        resultado = self._s.execute(
            update(Movimiento)
            .where(columna == origen_id)
            .values({columna.key: destino_id})
            .execution_options(synchronize_session=False)
        )
        return int(resultado.rowcount or 0)

    def _fusionar_tecnico(self, origen_id: int, destino_id: int) -> int:
        ya_vinculados = set(
            self._s.scalars(
                select(MovimientoTecnico.movimiento_id).where(
                    MovimientoTecnico.tecnico_id == destino_id
                )
            ).all()
        )
        vinculos = self._s.execute(
            select(MovimientoTecnico.movimiento_id, MovimientoTecnico.principal).where(
                MovimientoTecnico.tecnico_id == origen_id
            )
        ).all()

        movidos = 0
        for movimiento_id, principal in vinculos:
            self._s.execute(
                delete(MovimientoTecnico).where(
                    MovimientoTecnico.movimiento_id == movimiento_id,
                    MovimientoTecnico.tecnico_id == origen_id,
                )
            )
            if movimiento_id in ya_vinculados:
                continue
            self._s.add(
                MovimientoTecnico(
                    movimiento_id=movimiento_id,
                    tecnico_id=destino_id,
                    principal=principal,
                )
            )
            movidos += 1
        return movidos

    def historial(self, *, limite: int = 200) -> list[dict[str, Any]]:
        """El rastro de cambios de catálogo, lo más nuevo primero."""
        filas = self._s.scalars(
            select(AuditoriaCatalogo)
            .order_by(AuditoriaCatalogo.ocurrido_en.desc(), AuditoriaCatalogo.id.desc())
            .limit(limite)
        ).all()
        return [
            {
                "catalogo": fila.catalogo,
                "registro_id": fila.registro_id,
                "accion": fila.accion,
                "campo": fila.campo,
                "valor_anterior": fila.valor_anterior,
                "valor_nuevo": fila.valor_nuevo,
                "usuario": fila.usuario_etiqueta,
                "ocurrido_en": fila.ocurrido_en,
            }
            for fila in filas
        ]

    def _obtener(self, modelo: type[ModeloCatalogo], catalogo_id: int) -> ModeloCatalogo:
        fila = self._s.get(modelo, catalogo_id)
        if fila is None:
            raise CatalogoNoEncontrado(f"no existe {modelo.__tablename__} {catalogo_id}")
        return fila


__all__ = [
    "CAMPOS_AUDITABLES",
    "CatalogoNoEncontrado",
    "CatalogoRepository",
    "FechasInvalidas",
    "MovimientoNoEncontrado",
    "MovimientoRepository",
    "NombreDuplicado",
]


#: Names the catalogs get in the audit rows, so a row is readable on its own.
_DIMENSIONES: dict[type, str] = {Area: "area", Tecnico: "tecnico", TipoEquipo: "tipo_equipo"}


class UsuarioNoEncontrado(LookupError):
    """El usuario pedido no existe."""


class UsuarioDuplicado(ValueError):
    """Ya hay un usuario con ese nombre (sin distinguir mayúsculas)."""


class UsuarioRepository:
    """Cuentas de la aplicación y autenticación.

    La regla que hace útil a la auditoría: el nombre que se guarda en cada cambio
    sale de acá, de una cuenta con contraseña, no de un campo de texto.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def listar(self) -> list[UsuarioLeido]:
        filas = self._s.scalars(select(Usuario).order_by(Usuario.nombre)).all()
        return [UsuarioLeido.model_validate(fila) for fila in filas]

    def obtener(self, usuario_id: int) -> UsuarioLeido:
        return UsuarioLeido.model_validate(self._orm(usuario_id))

    def hay_administrador(self) -> bool:
        return bool(
            self._s.scalar(
                select(func.count())
                .select_from(Usuario)
                .where(Usuario.es_admin.is_(True), Usuario.activo.is_(True))
            )
        )

    def contar_activos(self) -> int:
        return int(
            self._s.scalar(
                select(func.count()).select_from(Usuario).where(Usuario.activo.is_(True))
            )
            or 0
        )

    def contar_administradores(self) -> int:
        return int(
            self._s.scalar(
                select(func.count())
                .select_from(Usuario)
                .where(Usuario.es_admin.is_(True), Usuario.activo.is_(True))
            )
            or 0
        )

    def cuenta_unica_con_clave(self) -> UsuarioLeido | None:
        """La única cuenta activa con contraseña, o ``None`` si no es única.

        Las cuentas de importación y de migración no tienen hash: no son personas y
        no cuentan como candidatas a entrar sin pedir contraseña.
        """
        filas = self._s.scalars(
            select(Usuario).where(
                Usuario.activo.is_(True), Usuario.password_hash.is_not(None)
            )
        ).all()
        if len(filas) != 1:
            return None
        return UsuarioLeido.model_validate(filas[0])

    def autenticar(self, nombre: str, clave: str) -> UsuarioLeido | None:
        """La cuenta, solo si el nombre existe, está activa y la clave coincide.

        Devuelve ``None`` en todos los casos de fallo, sin distinguir cuál fue:
        quien prueba contraseñas no tiene por qué enterarse de qué usuarios hay.
        """
        limpio = nombre.strip()
        if not limpio or not clave:
            return None
        fila = self._s.scalar(
            select(Usuario).where(func.lower(Usuario.nombre) == limpio.lower())
        )
        if fila is None or not fila.activo:
            return None
        if not verificar(fila.password_hash, clave):
            return None
        if necesita_rehash(fila.password_hash):
            # Los parámetros de argon2 suben con el tiempo; el que entra se
            # re-hashea mientras la contraseña está en la mano.
            fila.password_hash = hashear(clave)
        fila.ultimo_acceso = dt.datetime.now(dt.UTC)
        self._s.flush()
        return UsuarioLeido.model_validate(fila)

    def crear(
        self, nombre: str, clave: str, *, es_admin: bool = False
    ) -> UsuarioLeido:
        motivo = clave_aceptable(clave)
        if motivo:
            raise ValueError(motivo)
        limpio = nombre.strip()
        if not limpio:
            raise ValueError("hace falta un nombre de usuario")
        repetido = self._s.scalar(
            select(Usuario).where(func.lower(Usuario.nombre) == limpio.lower())
        )
        if repetido is not None:
            raise UsuarioDuplicado(f"ya existe un usuario «{repetido.nombre}»")
        fila = Usuario(
            nombre=limpio, password_hash=hashear(clave), es_admin=es_admin
        )
        self._s.add(fila)
        self._s.flush()
        return UsuarioLeido.model_validate(fila)

    def fijar_clave_de_existente(
        self, nombre: str, clave: str, *, es_admin: bool = True
    ) -> UsuarioLeido:
        """Da contraseña a una cuenta que ya existía sin ella.

        Es el caso de los usuarios que creó la importación o una migración: no son
        gente con contraseña, pero el nombre puede ser el de alguien real que ahora
        necesita entrar sin que queden dos cuentas con el mismo nombre.
        """
        motivo = clave_aceptable(clave)
        if motivo:
            raise ValueError(motivo)
        fila = self._s.scalar(
            select(Usuario).where(func.lower(Usuario.nombre) == nombre.strip().lower())
        )
        if fila is None:
            raise UsuarioNoEncontrado(nombre)
        fila.password_hash = hashear(clave)
        fila.es_admin = es_admin
        fila.activo = True
        self._s.flush()
        return UsuarioLeido.model_validate(fila)

    def cambiar_clave(self, usuario_id: int, clave: str) -> None:
        motivo = clave_aceptable(clave)
        if motivo:
            raise ValueError(motivo)
        self._orm(usuario_id).password_hash = hashear(clave)
        self._s.flush()

    def alternar_activo(self, usuario_id: int) -> UsuarioLeido:
        fila = self._orm(usuario_id)
        if fila.activo and fila.es_admin and self.contar_administradores() <= 1:
            raise ValueError(
                "no se puede desactivar al último administrador activo: "
                "nadie podría volver a administrar el sistema"
            )
        fila.activo = not fila.activo
        self._s.flush()
        return UsuarioLeido.model_validate(fila)

    def hacer_administrador(self, usuario_id: int, *, es_admin: bool) -> UsuarioLeido:
        fila = self._orm(usuario_id)
        if fila.es_admin and not es_admin and self.contar_administradores() <= 1:
            raise ValueError("no se puede quitar el último administrador activo")
        fila.es_admin = es_admin
        self._s.flush()
        return UsuarioLeido.model_validate(fila)

    def _orm(self, usuario_id: int) -> Usuario:
        fila = self._s.get(Usuario, usuario_id)
        if fila is None:
            raise UsuarioNoEncontrado(f"no existe el usuario {usuario_id}")
        return fila
