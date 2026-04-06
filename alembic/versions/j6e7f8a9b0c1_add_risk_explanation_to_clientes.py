"""add risk_explanation to clientes

Revision ID: j6e7f8a9b0c1
Revises: i5d6e7f8a9b0
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "j6e7f8a9b0c1"
down_revision = "i5d6e7f8a9b0"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "clientes",
        sa.Column("risk_explanation", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("clientes", "risk_explanation")
