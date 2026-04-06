"""create asistente_canales, asistente_mensajes, asistente_confirmaciones_pendientes

Revision ID: o1d2e3f4a5b6
Revises: n0c1d2e3f4a5
Create Date: 2026-04-04

"""
from alembic import op
import sqlalchemy as sa

revision = "o1d2e3f4a5b6"
down_revision = "n0c1d2e3f4a5"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "asistente_canales",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=True),
        sa.Column("tipo_usuario", sa.String(10), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(10), nullable=False),
        sa.Column("identificador", sa.String(255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_asistente_canales_lookup", "asistente_canales", ["canal", "identificador"])

    op.create_table(
        "asistente_mensajes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=True),
        sa.Column("tipo_usuario", sa.String(10), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(10), nullable=False),
        sa.Column("direccion", sa.String(10), nullable=False),
        sa.Column("contenido_raw", sa.Text(), nullable=False),
        sa.Column("contenido_procesado", sa.Text(), nullable=True),
        sa.Column("intencion_detectada", sa.String(100), nullable=True),
        sa.Column("entidades_extraidas", sa.JSON(), nullable=True),
        sa.Column("estado", sa.String(30), nullable=False, server_default="procesado"),
        sa.Column("error_detalle", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_asistente_mensajes_usuario", "asistente_mensajes", ["usuario_id", "canal"])

    op.create_table(
        "asistente_confirmaciones_pendientes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("canal", sa.String(10), nullable=False),
        sa.Column("operacion", sa.JSON(), nullable=False),
        sa.Column("expira_at", sa.DateTime(), nullable=False),
        sa.Column("confirmado", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("asistente_confirmaciones_pendientes")
    op.drop_index("ix_asistente_mensajes_usuario")
    op.drop_table("asistente_mensajes")
    op.drop_index("ix_asistente_canales_lookup")
    op.drop_table("asistente_canales")
