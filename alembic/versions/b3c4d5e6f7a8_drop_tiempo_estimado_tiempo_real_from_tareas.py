"""drop tiempo_estimado and tiempo_real from tareas

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-03-31 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('tareas', 'tiempo_estimado')
    op.drop_column('tareas', 'tiempo_real')


def downgrade() -> None:
    op.add_column('tareas', sa.Column('tiempo_real', sa.Integer(), nullable=True))
    op.add_column('tareas', sa.Column('tiempo_estimado', sa.Integer(), nullable=True))
