"""rbac: update RolEmpleado enum — rename socio->dueno, add rrhh

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
Create Date: 2026-04-02

"""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Migrar datos: socio → dueno
    op.execute("UPDATE empleados SET rol = 'dueno' WHERE rol = 'socio'")

    # 2. Recrear la columna con el nuevo enum (batch para compatibilidad SQLite)
    with op.batch_alter_table("empleados", schema=None) as batch_op:
        batch_op.alter_column(
            "rol",
            existing_type=sa.Enum("socio", "contador", "administrativo", name="rolempleado"),
            type_=sa.Enum("dueno", "contador", "administrativo", "rrhh", name="rolempleado"),
            existing_nullable=False,
        )


def downgrade():
    op.execute("UPDATE empleados SET rol = 'socio' WHERE rol = 'dueno'")

    with op.batch_alter_table("empleados", schema=None) as batch_op:
        batch_op.alter_column(
            "rol",
            existing_type=sa.Enum("dueno", "contador", "administrativo", "rrhh", name="rolempleado"),
            type_=sa.Enum("socio", "contador", "administrativo", name="rolempleado"),
            existing_nullable=False,
        )
