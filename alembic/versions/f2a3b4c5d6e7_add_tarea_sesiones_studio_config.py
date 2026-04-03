"""add tarea_sesiones and studio_config

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    # Nuevos campos en tareas
    op.add_column("tareas", sa.Column("tiempo_estimado_min", sa.Integer(), nullable=True))
    op.add_column("tareas", sa.Column("tiempo_real_min", sa.Integer(), nullable=False, server_default="0"))

    # Tabla tarea_sesiones
    op.create_table(
        "tarea_sesiones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tarea_id", sa.Integer(), sa.ForeignKey("tareas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empleado_id", sa.Integer(), sa.ForeignKey("empleados.id", ondelete="SET NULL"), nullable=True),
        sa.Column("inicio", sa.DateTime(), nullable=False),
        sa.Column("fin", sa.DateTime(), nullable=True),
        sa.Column("minutos", sa.Integer(), nullable=True),
    )

    # Tabla studio_config (singleton)
    op.create_table(
        "studio_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("tarifa_hora_pesos", sa.Numeric(10, 2), nullable=True),
        sa.Column("moneda", sa.String(10), nullable=False, server_default="ARS"),
        sa.Column("zona_horaria", sa.String(50), nullable=False, server_default="America/Argentina/Buenos_Aires"),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("studio_config")
    op.drop_table("tarea_sesiones")
    op.drop_column("tareas", "tiempo_real_min")
    op.drop_column("tareas", "tiempo_estimado_min")
