"""add missing condicionfiscal enum values

Revision ID: b73b03eac462
Revises: bb3aae8df077
Create Date: 2026-03-28 16:24:29.957209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b73b03eac462'
down_revision: Union[str, None] = 'bb3aae8df077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE condicionfiscal ADD VALUE IF NOT EXISTS 'relacion_de_dependencia'")
    op.execute("ALTER TYPE condicionfiscal ADD VALUE IF NOT EXISTS 'sujeto_no_categorizado'")


def downgrade() -> None:
    # PostgreSQL no permite eliminar valores de un enum con ALTER TYPE DROP VALUE
    pass
