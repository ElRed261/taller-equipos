"""auditoria de catalogo

Registra quién crea, renombra, activa, desactiva o fusiona un área, un tipo de
equipo o un técnico. Hasta ahora esos cambios no dejaban rastro en ninguna parte.

La tabla es un histórico: nunca se actualiza ni se borra, solo se agrega.

Revision ID: 7157073ef758
Revises: 5189c311d5b9
Create Date: 2026-11-02 09:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7157073ef758"
down_revision: str | Sequence[str] | None = "5189c311d5b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auditoria_catalogo",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("catalogo", sa.String(24), nullable=False),
        sa.Column("registro_id", sa.Integer(), nullable=False),
        sa.Column("accion", sa.String(16), nullable=False),
        sa.Column("campo", sa.String(64), nullable=False),
        sa.Column("valor_anterior", sa.Text(), nullable=True),
        sa.Column("valor_nuevo", sa.Text(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("usuario_etiqueta", sa.String(80), nullable=False),
        sa.Column(
            "ocurrido_en",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "accion in ('crear','renombrar','activar','desactivar','fusionar')",
            name="auditoria_catalogo_accion",
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_auditoria_catalogo_registro",
        "auditoria_catalogo",
        ["catalogo", "registro_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_auditoria_catalogo_registro", table_name="auditoria_catalogo")
    op.drop_table("auditoria_catalogo")
