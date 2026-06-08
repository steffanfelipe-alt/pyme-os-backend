"""Add studio_id to emails_entrantes for multi-tenancy isolation

Revision ID: a8b9c0d1e2f3
Revises: z7a8b9c0d1e2
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "z7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("emails_entrantes") as batch_op:
        batch_op.add_column(
            sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=True)
        )
        batch_op.create_index("ix_emails_entrantes_studio_id", ["studio_id"])


def downgrade():
    with op.batch_alter_table("emails_entrantes") as batch_op:
        batch_op.drop_index("ix_emails_entrantes_studio_id")
        batch_op.drop_column("studio_id")
