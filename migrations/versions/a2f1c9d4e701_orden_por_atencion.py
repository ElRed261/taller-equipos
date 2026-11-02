"""orden del grid: lo que necesita atencion, al final

El grid ahora ordena por una expresión booleana antes que por fecha: las filas
marcadas para revisión y las que tienen datos faltantes quedan al final. El índice
se rehace con la misma expresión, porque un índice con otra forma no se usa.

Revision ID: a2f1c9d4e701
Revises: 7157073ef758
Create Date: 2026-11-02 09:55:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a2f1c9d4e701"
down_revision: str | Sequence[str] | None = "7157073ef758"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ATENCION = (
    "(requiere_revision OR fecha_entrada IS NULL OR area_id IS NULL "
    "OR codigo_inventario IS NULL)"
)


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_movimiento_orden")
    op.execute(
        f"CREATE INDEX ix_movimiento_orden ON movimiento USING btree ("
        f"{ATENCION}, fecha_entrada DESC NULLS LAST, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_movimiento_orden")
    op.execute(
        "CREATE INDEX ix_movimiento_orden ON movimiento USING btree "
        "(fecha_entrada DESC NULLS LAST, id DESC)"
    )
