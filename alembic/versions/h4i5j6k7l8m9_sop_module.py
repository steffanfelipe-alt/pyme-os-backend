"""sop_module: tablas sop_documentos, sop_pasos, sop_revisiones, sop_confirmaciones_lectura

Revision ID: h4i5j6k7l8m9
Revises: g3b4c5d6e7f8
Create Date: 2026-04-03

"""
from alembic import op
import sqlalchemy as sa

revision = "h4i5j6k7l8m9"
down_revision = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sop_documentos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("titulo", sa.String(255), nullable=False),
        sa.Column(
            "area",
            sa.Enum(
                "administracion", "impuestos", "laboral", "atencion_cliente", "rrhh", "otro",
                name="areasop", native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("descripcion_proposito", sa.Text(), nullable=True),
        sa.Column("resultado_esperado", sa.Text(), nullable=True),
        sa.Column("empleado_creador_id", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=True),
        sa.Column("empleado_responsable_id", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("fecha_ultima_revision", sa.DateTime(), nullable=True),
        sa.Column(
            "estado",
            sa.Enum("borrador", "activo", "archivado", name="estadosop", native_enum=False),
            nullable=False,
            server_default="borrador",
        ),
        sa.Column("proceso_id", sa.Integer(), sa.ForeignKey("proceso_templates.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sop_pasos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sop_id", sa.Integer(), sa.ForeignKey("sop_documentos.id"), nullable=False),
        sa.Column("orden", sa.Integer(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=False),
        sa.Column("responsable_sugerido", sa.String(255), nullable=True),
        sa.Column("tiempo_estimado_minutos", sa.Integer(), nullable=True),
        sa.Column("recursos", sa.Text(), nullable=True),
        sa.Column("es_automatizable", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("requiere_confirmacion_lectura", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sop_revisiones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sop_id", sa.Integer(), sa.ForeignKey("sop_documentos.id"), nullable=False),
        sa.Column("fecha_revision", sa.DateTime(), nullable=False),
        sa.Column("descripcion_cambio", sa.Text(), nullable=True),
        sa.Column("empleado_id", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=True),
        sa.Column("version_resultante", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "sop_confirmaciones_lectura",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("sop_paso_id", sa.Integer(), sa.ForeignKey("sop_pasos.id"), nullable=False),
        sa.Column("empleado_id", sa.Integer(), sa.ForeignKey("empleados.id"), nullable=False),
        sa.Column(
            "proceso_instancia_paso_id",
            sa.Integer(),
            sa.ForeignKey("proceso_pasos_instancia.id"),
            nullable=True,
        ),
        sa.Column("fecha_confirmacion", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade():
    op.drop_table("sop_confirmaciones_lectura")
    op.drop_table("sop_revisiones")
    op.drop_table("sop_pasos")
    op.drop_table("sop_documentos")
