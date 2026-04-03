"""add informes_ejecutivos table

Revision ID: a1b2c3d4e5f6
Revises: 15c111649cad
Create Date: 2026-03-31 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '15c111649cad'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'informes_ejecutivos',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('periodo', sa.String(length=7), nullable=False),
        sa.Column('generado_por_id', sa.Integer(), nullable=True),
        sa.Column('resumen_vencimientos', sa.JSON(), nullable=True),
        sa.Column('resumen_workload', sa.JSON(), nullable=True),
        sa.Column('resumen_rentabilidad', sa.JSON(), nullable=True),
        sa.Column('resumen_alertas', sa.JSON(), nullable=True),
        sa.Column('resumen_riesgo', sa.JSON(), nullable=True),
        sa.Column('total_clientes_activos', sa.Integer(), nullable=True),
        sa.Column('alertas_criticas', sa.Integer(), nullable=True),
        sa.Column('clientes_riesgo_rojo', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['generado_por_id'], ['usuarios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('informes_ejecutivos')
