"""add telegram fields to studio_config

Revision ID: p2e3f4a5b6c7
Revises: o1d2e3f4a5b6
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "p2e3f4a5b6c7"
down_revision = "o1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("studio_config", sa.Column("telegram_chat_id", sa.Integer(), nullable=True))
    op.add_column("studio_config", sa.Column("telegram_active", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("studio_config", sa.Column("telegram_connect_code", sa.String(10), nullable=True))
    op.add_column("studio_config", sa.Column("telegram_connect_expires_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("studio_config", "telegram_connect_expires_at")
    op.drop_column("studio_config", "telegram_connect_code")
    op.drop_column("studio_config", "telegram_active")
    op.drop_column("studio_config", "telegram_chat_id")
