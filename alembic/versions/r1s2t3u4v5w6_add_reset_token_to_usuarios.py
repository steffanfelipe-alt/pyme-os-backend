"""add reset_token to usuarios

Revision ID: r1s2t3u4v5w6
Revises: ec43e60942ec, q3r4s5t6u7v8
Create Date: 2026-04-06 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r1s2t3u4v5w6"
down_revision: Union[str, tuple] = ("ec43e60942ec", "q3r4s5t6u7v8")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuarios", sa.Column("reset_token", sa.String(255), nullable=True))
    op.add_column("usuarios", sa.Column("reset_token_expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("usuarios", "reset_token_expires_at")
    op.drop_column("usuarios", "reset_token")
