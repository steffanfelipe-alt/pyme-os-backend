"""add ai_interpretation to informes_ejecutivos

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "i5d6e7f8a9b0"
down_revision = "h4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "informes_ejecutivos",
        sa.Column("ai_interpretation", sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_column("informes_ejecutivos", "ai_interpretation")
