"""add assistant_conversations and email_log tables, drop tarea legacy fields

Revision ID: q3r4s5t6u7v8
Revises: p2e3f4a5b6c7
Create Date: 2026-04-05

"""
from alembic import op
import sqlalchemy as sa

revision = "q3r4s5t6u7v8"
down_revision = None  # will be set by alembic
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- assistant_conversations ---
    op.create_table(
        "assistant_conversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(50), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("has_disclaimer", sa.Boolean(), default=False, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    # --- email_log ---
    op.create_table(
        "email_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=True),
        sa.Column("recipient_type", sa.String(10), nullable=False),
        sa.Column("recipient_email", sa.String(255), nullable=False),
        sa.Column("email_type", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(20), server_default="sent", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )

    # --- Drop legacy tarea fields ---
    op.drop_column("tareas", "tiempo_estimado_min")
    op.drop_column("tareas", "tiempo_real_min")


def downgrade() -> None:
    op.add_column("tareas", sa.Column("tiempo_estimado_min", sa.Integer(), nullable=True))
    op.add_column("tareas", sa.Column("tiempo_real_min", sa.Integer(), nullable=False, server_default="0"))
    op.drop_table("email_log")
    op.drop_table("assistant_conversations")
