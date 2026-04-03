"""add proceso conocimiento module

Revision ID: e1f2a3b4c5d6
Revises: d5e6f7a8b9c0
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proceso_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nombre", sa.String(255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column(
            "tipo",
            sa.Enum(
                "onboarding", "liquidacion_iva", "balance", "cierre_ejercicio",
                "declaracion_ganancias", "declaracion_iibb", "otro",
                name="tipoproceso", native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("tiempo_estimado_minutos", sa.Integer(), nullable=True),
        sa.Column("sop_url", sa.String(500), nullable=True),
        sa.Column("sop_version", sa.Integer(), default=1, nullable=False),
        sa.Column("activo", sa.Boolean(), default=True, nullable=False),
        sa.Column("creado_por", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "proceso_pasos_template",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("proceso_templates.id"), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.Column("tiempo_estimado_minutos", sa.Integer(), nullable=True),
        sa.Column("es_automatizable", sa.Boolean(), default=False, nullable=False),
        sa.UniqueConstraint("template_id", "orden", name="uq_template_orden"),
    )

    op.create_table(
        "proceso_instancias",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("proceso_templates.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=True),
        sa.Column("vencimiento_id", sa.Integer(), sa.ForeignKey("vencimientos.id"), nullable=True),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente", "en_progreso", "completado", "cancelado",
                name="estadoinstancia", native_enum=False,
            ),
            default="pendiente",
            nullable=False,
        ),
        sa.Column("progreso_pct", sa.Float(), default=0.0, nullable=False),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=True),
        sa.Column("fecha_fin", sa.DateTime(), nullable=True),
        sa.Column("creado_por", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "proceso_pasos_instancia",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instancia_id", sa.Integer(), sa.ForeignKey("proceso_instancias.id"), nullable=False),
        sa.Column("paso_template_id", sa.Integer(), sa.ForeignKey("proceso_pasos_template.id"), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "pendiente", "en_progreso", "completado",
                name="estadopasoinstancia", native_enum=False,
            ),
            default="pendiente",
            nullable=False,
        ),
        sa.Column("fecha_inicio", sa.DateTime(), nullable=True),
        sa.Column("fecha_fin", sa.DateTime(), nullable=True),
        sa.Column("tiempo_real_minutos", sa.Float(), nullable=True),
        sa.Column("notas", sa.Text(), nullable=True),
        sa.Column("asignado_a", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=True),
    )

    op.create_table(
        "automatizaciones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("proceso_templates.id"), nullable=False, unique=True),
        sa.Column("flujo_json", sa.JSON(), nullable=True),
        sa.Column("analisis_pasos", sa.JSON(), nullable=True),
        sa.Column("ahorro_horas_mes", sa.Float(), default=0.0, nullable=False),
        sa.Column("herramienta", sa.String(50), default="n8n", nullable=False),
        sa.Column(
            "estado",
            sa.Enum(
                "borrador", "activa", "pausada",
                name="estadoautomatizacion", native_enum=False,
            ),
            default="borrador",
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("automatizaciones")
    op.drop_table("proceso_pasos_instancia")
    op.drop_table("proceso_instancias")
    op.drop_table("proceso_pasos_template")
    op.drop_table("proceso_templates")
