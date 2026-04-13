"""add api keys and smtp fields to studio_config

Revision ID: u2v3w4x5y6z7
Revises: t1u2v3w4x5y6
Create Date: 2026-04-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u2v3w4x5y6z7"
down_revision: Union[str, None] = "t1u2v3w4x5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("studio_config", sa.Column("telegram_bot_token", sa.String(255), nullable=True))
    op.add_column("studio_config", sa.Column("telegram_webhook_url", sa.String(500), nullable=True))
    op.add_column("studio_config", sa.Column("anthropic_api_key", sa.String(255), nullable=True))
    op.add_column("studio_config", sa.Column("smtp_host", sa.String(255), nullable=True))
    op.add_column("studio_config", sa.Column("smtp_port", sa.Integer(), nullable=True))
    op.add_column("studio_config", sa.Column("smtp_user", sa.String(255), nullable=True))
    op.add_column("studio_config", sa.Column("smtp_password", sa.String(255), nullable=True))
    op.add_column("studio_config", sa.Column("smtp_from", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("studio_config", "smtp_from")
    op.drop_column("studio_config", "smtp_password")
    op.drop_column("studio_config", "smtp_user")
    op.drop_column("studio_config", "smtp_port")
    op.drop_column("studio_config", "smtp_host")
    op.drop_column("studio_config", "anthropic_api_key")
    op.drop_column("studio_config", "telegram_webhook_url")
    op.drop_column("studio_config", "telegram_bot_token")
