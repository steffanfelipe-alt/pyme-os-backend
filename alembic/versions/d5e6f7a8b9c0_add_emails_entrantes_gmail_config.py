"""add emails_entrantes and gmail_config tables

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-04-02

"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "gmail_config",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_email", sa.String(255), nullable=False, unique=True),
        sa.Column("gmail_address", sa.String(255), nullable=False),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column("refresh_token_enc", sa.Text(), nullable=False),
        sa.Column("token_expiry", sa.DateTime(), nullable=True),
        sa.Column("watch_expiry", sa.DateTime(), nullable=True),
        sa.Column("watch_history_id", sa.String(50), nullable=True),
        sa.Column("activo", sa.Boolean(), default=True, nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "emails_entrantes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("remitente", sa.String(255), nullable=False),
        sa.Column("asunto", sa.String(500), nullable=True),
        sa.Column("cuerpo_texto", sa.Text(), nullable=True),
        sa.Column("cuerpo_html", sa.Text(), nullable=True),
        sa.Column("tiene_adjuntos", sa.Boolean(), default=False, nullable=False),
        sa.Column("fecha_recibido", sa.DateTime(), nullable=False),
        sa.Column("gmail_message_id", sa.String(200), nullable=True, unique=True),
        sa.Column("categoria", sa.String(50), nullable=True),
        sa.Column("urgencia", sa.String(10), nullable=True),
        sa.Column("resumen", sa.Text(), nullable=True),
        sa.Column("remitente_tipo", sa.String(30), nullable=True),
        sa.Column("confianza_clasificacion", sa.Float(), nullable=True),
        sa.Column("requiere_respuesta", sa.Boolean(), default=False, nullable=False),
        sa.Column("requiere_revision_manual", sa.Boolean(), default=False, nullable=False),
        sa.Column("motivo_revision", sa.String(100), nullable=True),
        sa.Column("borrador_respuesta", sa.Text(), nullable=True),
        sa.Column("borrador_aprobado", sa.Boolean(), default=False, nullable=False),
        sa.Column("borrador_editado", sa.Text(), nullable=True),
        sa.Column("respuesta_enviada_at", sa.DateTime(), nullable=True),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("asignado_a", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=True),
        sa.Column("estado", sa.String(20), default="no_leido", nullable=False),
        sa.Column("leido_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("emails_entrantes")
    op.drop_table("gmail_config")
