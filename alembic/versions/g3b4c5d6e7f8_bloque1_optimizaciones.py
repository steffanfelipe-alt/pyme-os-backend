"""bloque1: umbral optimizador, ciclo vida automatizaciones, FK tarea-paso

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa

revision = "g3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade():
    # 1.1 — Umbral configurable en studio_config
    op.add_column(
        "studio_config",
        sa.Column("umbral_instancias_optimizador", sa.Integer(), nullable=False, server_default="5"),
    )

    # 1.2 — Ciclo de vida en automatizaciones
    op.add_column(
        "automatizaciones",
        sa.Column(
            "estado_revision",
            sa.Enum("pendiente", "aprobada", "descartada", name="estadorevisionautomatizacion", native_enum=False),
            nullable=False,
            server_default="pendiente",
        ),
    )
    op.add_column("automatizaciones", sa.Column("aprobado_at", sa.DateTime(), nullable=True))
    op.add_column("automatizaciones", sa.Column("motivo_descarte", sa.Text(), nullable=True))

    # 1.3 — FK tarea → proceso_pasos_instancia
    op.add_column(
        "tareas",
        sa.Column(
            "proceso_instancia_paso_id",
            sa.Integer(),
            sa.ForeignKey("proceso_pasos_instancia.id"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("tareas", "proceso_instancia_paso_id")
    op.drop_column("automatizaciones", "motivo_descarte")
    op.drop_column("automatizaciones", "aprobado_at")
    op.drop_column("automatizaciones", "estado_revision")
    op.drop_column("studio_config", "umbral_instancias_optimizador")
