"""add costo_estimado and profit_margin_percentage to rentabilidad_mensual

Revision ID: k7f8a9b0c1d2
Revises: j6e7f8a9b0c1
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "k7f8a9b0c1d2"
down_revision = "j6e7f8a9b0c1"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "rentabilidad_mensual",
        sa.Column("costo_estimado", sa.Float(), nullable=True),
    )
    op.add_column(
        "rentabilidad_mensual",
        sa.Column("profit_margin_percentage", sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_column("rentabilidad_mensual", "profit_margin_percentage")
    op.drop_column("rentabilidad_mensual", "costo_estimado")
