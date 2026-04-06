"""add umbral_dias_notificacion to studio_config

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "h4c5d6e7f8a9"
down_revision = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "studio_config",
        sa.Column("umbral_dias_notificacion", sa.Integer(), nullable=False, server_default="7"),
    )


def downgrade():
    op.drop_column("studio_config", "umbral_dias_notificacion")
