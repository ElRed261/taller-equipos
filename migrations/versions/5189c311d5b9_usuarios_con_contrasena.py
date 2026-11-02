"""usuarios con contrasena

Alembic quiso incluir un cambio de índice sobre ``movimiento`` que no tiene nada
que ver con esta tarea: se quitó a mano. Una migración cuenta un solo cambio, para
poder leerla y revertirla sin adivinar.

Las cuentas que ya existen (importación, migraciones) quedan sin contraseña y sin
ser administradoras: no son personas, y sin hash no pueden entrar.

Revision ID: 5189c311d5b9
Revises: 99746ce93516
Create Date: 2026-11-02 09:09:28.733173

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5189c311d5b9"
down_revision: str | Sequence[str] | None = "99746ce93516"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "usuario",
        sa.Column("es_admin", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "usuario",
        sa.Column("ultimo_acceso", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("usuario", "ultimo_acceso")
    op.drop_column("usuario", "es_admin")
    op.drop_column("usuario", "password_hash")
