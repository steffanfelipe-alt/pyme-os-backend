"""fix proceso missing columns: version_anterior_json and tiempo_real_minutos

Revision ID: t1u2v3w4x5y6
Revises: s2t3u4v5w6x7
Create Date: 2026-04-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, None] = "s2t3u4v5w6x7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # proceso_templates was created without version_anterior_json —
    # every ORM SELECT on ProcesoTemplate fails until this column exists in the DB.
    op.add_column(
        "proceso_templates",
        sa.Column("version_anterior_json", sa.JSON(), nullable=True),
    )
    # proceso_instancias was created without tiempo_real_minutos —
    # completar_instancia() in proceso_service.py sets this field and crashes without it.
    op.add_column(
        "proceso_instancias",
        sa.Column("tiempo_real_minutos", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("proceso_instancias", "tiempo_real_minutos")
    op.drop_column("proceso_templates", "version_anterior_json")
