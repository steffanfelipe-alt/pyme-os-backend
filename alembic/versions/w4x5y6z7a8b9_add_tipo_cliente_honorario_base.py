"""add tipo_cliente and honorario_base to clientes

Revision ID: w4x5y6z7a8b9
Revises: v3w4x5y6z7a8
Create Date: 2026-04-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w4x5y6z7a8b9"
down_revision: Union[str, None] = "v3w4x5y6z7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Crear tipo enum en PostgreSQL
    tipo_cliente_enum = sa.Enum(
        "monotributista", "responsable_inscripto", "sociedad", "empleador", "otro",
        name="tipo_cliente_enum",
    )
    tipo_cliente_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "clientes",
        sa.Column("tipo_cliente", tipo_cliente_enum, server_default="otro", nullable=False),
    )
    op.add_column(
        "clientes",
        sa.Column("honorario_base", sa.Numeric(10, 2), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("clientes", "honorario_base")
    op.drop_column("clientes", "tipo_cliente")

    tipo_cliente_enum = sa.Enum(name="tipo_cliente_enum")
    tipo_cliente_enum.drop(op.get_bind(), checkfirst=True)
