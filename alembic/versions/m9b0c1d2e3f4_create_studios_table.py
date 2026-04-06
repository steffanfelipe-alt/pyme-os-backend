"""create studios table with default row

Revision ID: m9b0c1d2e3f4
Revises: l8a9b0c1d2e3
Create Date: 2026-04-04

"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import text

revision = "m9b0c1d2e3f4"
down_revision = "l8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "studios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    # Seed: un registro por defecto (id=1)
    nombre = os.environ.get("STUDIO_NAME", "Estudio Principal")
    op.execute(text("INSERT INTO studios (nombre) VALUES (:n)"), {"n": nombre})


def downgrade():
    op.drop_table("studios")
