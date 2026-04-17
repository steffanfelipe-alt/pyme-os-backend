"""add portal_tokens solicitudes_documentos_auto abonos cobros

Revision ID: y6z7a8b9c0d1
Revises: x5y6z7a8b9c0
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "y6z7a8b9c0d1"
down_revision = "x5y6z7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    # E1 — Portal tokens
    op.create_table(
        "portal_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("expira_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_portal_tokens_studio_id", "portal_tokens", ["studio_id"])
    op.create_index("ix_portal_tokens_cliente_id", "portal_tokens", ["cliente_id"])
    op.create_index("ix_portal_tokens_token", "portal_tokens", ["token"])

    # E2 — Solicitudes documentos auto
    estado_solicitud_enum = sa.Enum(
        "pendiente", "enviada", "recibida", "vencida",
        name="estado_solicitud_enum"
    )
    op.create_table(
        "solicitudes_documentos_auto",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("vencimiento_id", sa.Integer(), sa.ForeignKey("vencimientos.id"), nullable=False),
        sa.Column("tipo_documento", sa.String(50), nullable=False),
        sa.Column("estado", estado_solicitud_enum, nullable=False, server_default="pendiente"),
        sa.Column("canal", sa.String(20), nullable=True),
        sa.Column("enviada_at", sa.DateTime(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_solicitudes_studio_id", "solicitudes_documentos_auto", ["studio_id"])
    op.create_index("ix_solicitudes_cliente_id", "solicitudes_documentos_auto", ["cliente_id"])

    # F1 — Abonos
    periodicidad_enum = sa.Enum(
        "mensual", "bimestral", "trimestral", "semestral", "anual",
        name="periodicidad_abono_enum"
    )
    op.create_table(
        "abonos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("concepto", sa.String(255), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("periodicidad", periodicidad_enum, nullable=False, server_default="mensual"),
        sa.Column("fecha_inicio", sa.Date(), nullable=False),
        sa.Column("fecha_proximo_cobro", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_abonos_studio_id", "abonos", ["studio_id"])
    op.create_index("ix_abonos_cliente_id", "abonos", ["cliente_id"])

    # F1 — Cobros
    estado_cobro_enum = sa.Enum(
        "pendiente", "cobrado", "vencido",
        name="estado_cobro_enum"
    )
    op.create_table(
        "cobros",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("abono_id", sa.Integer(), sa.ForeignKey("abonos.id"), nullable=False),
        sa.Column("fecha_cobro", sa.Date(), nullable=False),
        sa.Column("monto", sa.Numeric(12, 2), nullable=False),
        sa.Column("estado", estado_cobro_enum, nullable=False, server_default="pendiente"),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_cobros_studio_id", "cobros", ["studio_id"])
    op.create_index("ix_cobros_abono_id", "cobros", ["abono_id"])


def downgrade():
    op.drop_table("cobros")
    op.drop_table("abonos")
    op.drop_table("solicitudes_documentos_auto")
    op.drop_table("portal_tokens")
    # Drop enums (only relevant for PostgreSQL)
    op.execute("DROP TYPE IF EXISTS estado_cobro_enum")
    op.execute("DROP TYPE IF EXISTS periodicidad_abono_enum")
    op.execute("DROP TYPE IF EXISTS estado_solicitud_enum")
