"""create dashboard_conversations table

Revision ID: n0c1d2e3f4a5
Revises: m9b0c1d2e3f4
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "n0c1d2e3f4a5"
down_revision = "m9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "dashboard_conversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=True),
        sa.Column("session_id", sa.String(50), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_dashboard_conv_session", "dashboard_conversations", ["session_id"])
    op.create_index("ix_dashboard_conv_studio", "dashboard_conversations", ["studio_id"])


def downgrade():
    op.drop_index("ix_dashboard_conv_studio")
    op.drop_index("ix_dashboard_conv_session")
    op.drop_table("dashboard_conversations")
