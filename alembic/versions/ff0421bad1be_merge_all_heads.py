"""merge all heads

Revision ID: ff0421bad1be
Revises: b3c4d5e6f7a8, h4i5j6k7l8m9, p2e3f4a5b6c7
Create Date: 2026-04-05 08:15:49.425107

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff0421bad1be'
down_revision: Union[str, None] = ('b3c4d5e6f7a8', 'h4i5j6k7l8m9', 'p2e3f4a5b6c7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
