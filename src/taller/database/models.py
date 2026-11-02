"""ORM models for the workshop database.

Design notes that are cheap to break and expensive to rediscover:

* ``Movimiento.fecha_entrada`` and ``fecha_salida`` are ``DATE``, not
  ``TIMESTAMPTZ``. Every one of the 1136 business dates in the legacy source is
  ``12:00:00 a. m.``, so a timestamp would promise a precision that does not
  exist and would reintroduce timezone ambiguity. ``creado_en`` and
  ``actualizado_en`` keep ``TIMESTAMPTZ`` because those are real instants.
* The green/red indicator is **not** a column. It is derived from
  ``fecha_salida`` (see the ``v_movimiento_estado`` view in the first
  migration), so it cannot desynchronise when someone edits a row.
* ``requiere_revision`` is the only way a row may bypass the date-order CHECK,
  and only imported rows may carry it (``ck_movimiento_revision_solo_legado``).
* ``codigo_inventario`` is an attribute, not an identity: the source has 303
  distinct values, 15 empty ones, and legitimate duplicates from re-intakes.
  There is deliberately no ``equipo`` entity to key on.
"""

from __future__ import annotations

import datetime as dt
from typing import Final

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ORIGEN_APP: Final = "app"
ORIGEN_CSV_V1: Final = "csv_v1"
ORIGENES: Final = (ORIGEN_APP, ORIGEN_CSV_V1)


class Base(DeclarativeBase):
    """Declarative base for every table in the schema."""


class TipoEquipo(Base):
    __tablename__ = "tipo_equipo"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    creado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Area(Base):
    __tablename__ = "area"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    creado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Tecnico(Base):
    __tablename__ = "tecnico"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    creado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Usuario(Base):
    """Application user, and the person the audit attributes changes to.

    ``password_hash`` is nullable because rows created by a migration or by the
    import are not people: they attribute a bulk change, and nobody may log in as
    them. A user without a hash simply cannot authenticate.
    """

    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    nombre: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    es_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    ultimo_acceso: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    creado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Movimiento(Base):
    """One intake/dispatch ticket for an equipment unit."""

    __tablename__ = "movimiento"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)

    fecha_entrada: Mapped[dt.date | None] = mapped_column(Date, default=None)
    fecha_salida: Mapped[dt.date | None] = mapped_column(Date, default=None)

    tipo_equipo_id: Mapped[int | None] = mapped_column(
        ForeignKey("tipo_equipo.id", ondelete="RESTRICT"), default=None
    )
    area_id: Mapped[int | None] = mapped_column(
        ForeignKey("area.id", ondelete="RESTRICT"), default=None
    )

    modelo: Mapped[str | None] = mapped_column(String(150), default=None)
    codigo_inventario: Mapped[str | None] = mapped_column(String(60), default=None)
    service_tag: Mapped[str | None] = mapped_column(String(60), default=None)
    diagnostico: Mapped[str | None] = mapped_column(Text, default=None)
    nota: Mapped[str | None] = mapped_column(Text, default=None)

    fecha_entrada_inferida: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    requiere_revision: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    revisado_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    origen: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text(f"'{ORIGEN_APP}'")
    )
    legacy_linea: Mapped[int | None] = mapped_column(Integer, default=None)

    creado_por_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), default=None
    )
    creado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actualizado_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        CheckConstraint(
            "requiere_revision"
            " OR fecha_entrada IS NULL"
            " OR fecha_salida IS NULL"
            " OR fecha_salida >= fecha_entrada",
            name="ck_movimiento_fechas",
        ),
        CheckConstraint(
            f"NOT requiere_revision OR origen <> '{ORIGEN_APP}'",
            name="ck_movimiento_revision_solo_legado",
        ),
        CheckConstraint(
            "origen IN ('app', 'csv_v1')",
            name="ck_movimiento_origen",
        ),
        UniqueConstraint("origen", "legacy_linea", name="uq_movimiento_legacy"),
        Index("ix_movimiento_orden", text("fecha_entrada DESC NULLS LAST, id DESC")),
        Index(
            "ix_movimiento_pendientes",
            "fecha_entrada",
            postgresql_where=text("fecha_salida IS NULL"),
        ),
        Index("ix_movimiento_revision", "id", postgresql_where=text("requiere_revision")),
        Index("ix_movimiento_inventario", "codigo_inventario"),
    )


class MovimientoTecnico(Base):
    """Many-to-many link: a movement may have several technicians."""

    __tablename__ = "movimiento_tecnico"

    movimiento_id: Mapped[int] = mapped_column(
        ForeignKey("movimiento.id", ondelete="RESTRICT"), primary_key=True
    )
    tecnico_id: Mapped[int] = mapped_column(
        ForeignKey("tecnico.id", ondelete="RESTRICT"), primary_key=True
    )
    principal: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))


class AuditoriaEdicion(Base):
    """Field-level audit trail written by the application and by the trigger."""

    __tablename__ = "auditoria_edicion"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    movimiento_id: Mapped[int] = mapped_column(
        ForeignKey("movimiento.id", ondelete="RESTRICT"), nullable=False
    )
    campo: Mapped[str] = mapped_column(String(64), nullable=False)
    valor_anterior: Mapped[str | None] = mapped_column(Text, default=None)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, default=None)
    usuario_id: Mapped[int | None] = mapped_column(
        ForeignKey("usuario.id", ondelete="RESTRICT"), default=None
    )
    usuario_etiqueta: Mapped[str] = mapped_column(String(80), nullable=False)
    ocurrido_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_auditoria_movimiento", "movimiento_id", text("ocurrido_en DESC")),)


class MapeoLegacy(Base):
    """Versioned alias map used by the ETL, one row per dirty source value."""

    __tablename__ = "mapeo_legacy"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)
    valor_origen: Mapped[str] = mapped_column(Text, nullable=False)
    destino_id: Mapped[int | None] = mapped_column(Integer, default=None)
    motivo: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        CheckConstraint(
            "dimension IN ('area', 'tecnico', 'tipo_equipo')",
            name="ck_mapeo_dimension",
        ),
        UniqueConstraint("dimension", "valor_origen", name="uq_mapeo_origen"),
    )


class Importacion(Base):
    """One ETL run, keyed by the SHA-256 of the source file for idempotency."""

    __tablename__ = "importacion"

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    archivo: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    filas_leidas: Mapped[int] = mapped_column(Integer, nullable=False)
    filas_insertadas: Mapped[int] = mapped_column(Integer, nullable=False)
    filas_con_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    filas_rechazadas: Mapped[int] = mapped_column(Integer, nullable=False)
    notas: Mapped[str | None] = mapped_column(Text, default=None)
    ejecutada_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ViewBase(DeclarativeBase):
    """Separate declarative base for classes mapped to a database view.

    A view mapping must stay out of ``Base.metadata``: if it entered it, the next
    ``alembic revision --autogenerate`` would emit ``CREATE TABLE
    v_movimiento_estado`` and the migration would fail against the existing view.
    """


class MovimientoEstado(ViewBase):
    """Read-only mapping of ``v_movimiento_estado``.

    ``estado`` is computed by the database from ``fecha_salida``. There is no
    writer for this class on purpose: the green/red indicator must never be
    something a user can set.
    """

    __tablename__ = "v_movimiento_estado"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fecha_entrada: Mapped[dt.date | None] = mapped_column(Date)
    fecha_salida: Mapped[dt.date | None] = mapped_column(Date)
    tipo_equipo_id: Mapped[int | None] = mapped_column(Integer)
    area_id: Mapped[int | None] = mapped_column(Integer)
    modelo: Mapped[str | None] = mapped_column(String(150))
    codigo_inventario: Mapped[str | None] = mapped_column(String(60))
    service_tag: Mapped[str | None] = mapped_column(String(60))
    diagnostico: Mapped[str | None] = mapped_column(Text)
    nota: Mapped[str | None] = mapped_column(Text)
    fecha_entrada_inferida: Mapped[bool] = mapped_column(Boolean)
    requiere_revision: Mapped[bool] = mapped_column(Boolean)
    revisado_en: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    origen: Mapped[str] = mapped_column(String(16))
    legacy_linea: Mapped[int | None] = mapped_column(Integer)
    creado_por_id: Mapped[int | None] = mapped_column(Integer)
    creado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    actualizado_en: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    estado: Mapped[str] = mapped_column(String(16))


class MovimientoEliminado(Base):
    """Snapshot of a movement deleted from the application.

    The row it describes is gone, so this table has no foreign key: it is the only
    trace left. It exists so an administrator can delete a record without the
    system losing the ability to say what was deleted, by whom, and when.
    """

    __tablename__ = "movimiento_eliminado"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    movimiento_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_etiqueta: Mapped[str] = mapped_column(String(80), nullable=False)
    ocurrido_en: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_movimiento_eliminado_ocurrido", text("ocurrido_en DESC")),)
