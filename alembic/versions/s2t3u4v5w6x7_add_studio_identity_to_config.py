"""add nombre_estudio and email_estudio to studio_config

Revision ID: s2t3u4v5w6x7
Revises: r1s2t3u4v5w6
Create Date: 2026-04-06 21:10:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s2t3u4v5w6x7"
down_revision: Union[str, None] = "r1s2t3u4v5w6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("studio_config", sa.Column("nombre_estudio", sa.String(255), nullable=True))
    op.add_column("studio_config", sa.Column("email_estudio", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("studio_config", "email_estudio")
    op.drop_column("studio_config", "nombre_estudio")
