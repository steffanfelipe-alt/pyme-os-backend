"""add es_urgente and es_importante to tareas (Eisenhower matrix)

Revision ID: x5y6z7a8b9c0
Revises: w4x5y6z7a8b9
Create Date: 2026-04-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x5y6z7a8b9c0"
down_revision: Union[str, None] = "w4x5y6z7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tareas",
        sa.Column("es_urgente", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "tareas",
        sa.Column("es_importante", sa.Boolean(), nullable=False, server_default="false"),
    )
    # Índice en cliente_id (ya existe la columna, solo el índice faltaba)
    op.create_index("idx_tareas_cliente_id", "tareas", ["cliente_id"])


def downgrade() -> None:
    op.drop_index("idx_tareas_cliente_id", "tareas")
    op.drop_column("tareas", "es_importante")
    op.drop_column("tareas", "es_urgente")
