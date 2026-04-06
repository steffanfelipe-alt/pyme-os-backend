"""add channel fields to alertas_vencimiento

Revision ID: l8a9b0c1d2e3
Revises: k7f8a9b0c1d2
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "l8a9b0c1d2e3"
down_revision = "k7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("alertas_vencimiento", sa.Column("sent_via_telegram", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("alertas_vencimiento", sa.Column("sent_via_email", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("alertas_vencimiento", sa.Column("telegram_sent_at", sa.DateTime(), nullable=True))
    op.add_column("alertas_vencimiento", sa.Column("email_sent_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("alertas_vencimiento", "email_sent_at")
    op.drop_column("alertas_vencimiento", "telegram_sent_at")
    op.drop_column("alertas_vencimiento", "sent_via_email")
    op.drop_column("alertas_vencimiento", "sent_via_telegram")
