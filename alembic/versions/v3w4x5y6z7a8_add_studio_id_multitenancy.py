"""add studio_id to all core tables — multi-tenancy

Revision ID: v3w4x5y6z7a8
Revises: u2v3w4x5y6z7
Create Date: 2026-04-12

Adds studio_id (FK → studios.id) to every tenant-scoped table.
Existing rows get studio_id = 1 (the seed studio).
Unique constraints that were global are narrowed to per-studio scope.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v3w4x5y6z7a8"
down_revision: Union[str, None] = "u2v3w4x5y6z7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── usuarios ────────────────────────────────────────────────────────────────
    op.add_column("usuarios", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE usuarios SET studio_id = 1")
    op.alter_column("usuarios", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_usuarios_studio_id", "usuarios", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_usuarios_studio_id", "usuarios", ["studio_id"])

    # ── empleados ───────────────────────────────────────────────────────────────
    op.add_column("empleados", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE empleados SET studio_id = 1")
    op.alter_column("empleados", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_empleados_studio_id", "empleados", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_empleados_studio_id", "empleados", ["studio_id"])
    # email ya no puede ser unique global — puede existir el mismo email en distinto studio
    op.drop_constraint("empleados_email_key", "empleados", type_="unique")
    op.create_unique_constraint(
        "uq_empleados_email_studio", "empleados", ["email", "studio_id"]
    )

    # ── clientes ────────────────────────────────────────────────────────────────
    op.add_column("clientes", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE clientes SET studio_id = 1")
    op.alter_column("clientes", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_clientes_studio_id", "clientes", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_clientes_studio_id", "clientes", ["studio_id"])
    # cuit_cuil: de unique global → unique por studio
    op.drop_constraint("clientes_cuit_cuil_key", "clientes", type_="unique")
    op.create_unique_constraint(
        "uq_clientes_cuit_studio", "clientes", ["cuit_cuil", "studio_id"]
    )

    # ── vencimientos ────────────────────────────────────────────────────────────
    op.add_column("vencimientos", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE vencimientos SET studio_id = 1")
    op.alter_column("vencimientos", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_vencimientos_studio_id", "vencimientos", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_vencimientos_studio_id", "vencimientos", ["studio_id"])

    # ── tareas ──────────────────────────────────────────────────────────────────
    op.add_column("tareas", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE tareas SET studio_id = 1")
    op.alter_column("tareas", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_tareas_studio_id", "tareas", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_tareas_studio_id", "tareas", ["studio_id"])

    # ── proceso_templates ───────────────────────────────────────────────────────
    op.add_column("proceso_templates", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE proceso_templates SET studio_id = 1")
    op.alter_column("proceso_templates", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_proceso_templates_studio_id", "proceso_templates", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_proceso_templates_studio_id", "proceso_templates", ["studio_id"])

    # ── proceso_instancias ──────────────────────────────────────────────────────
    op.add_column("proceso_instancias", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE proceso_instancias SET studio_id = 1")
    op.alter_column("proceso_instancias", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_proceso_instancias_studio_id", "proceso_instancias", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_proceso_instancias_studio_id", "proceso_instancias", ["studio_id"])

    # ── alertas_vencimiento ─────────────────────────────────────────────────────
    op.add_column("alertas_vencimiento", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE alertas_vencimiento SET studio_id = 1")
    op.alter_column("alertas_vencimiento", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_alertas_studio_id", "alertas_vencimiento", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_alertas_studio_id", "alertas_vencimiento", ["studio_id"])

    # ── automatizacion_python ───────────────────────────────────────────────────
    op.add_column("automatizaciones_python", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE automatizaciones_python SET studio_id = 1")
    op.alter_column("automatizaciones_python", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_automatizaciones_python_studio_id", "automatizaciones_python", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_automatizaciones_python_studio_id", "automatizaciones_python", ["studio_id"])

    # ── plantillas_vencimiento ──────────────────────────────────────────────────
    op.add_column("plantillas_vencimiento", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE plantillas_vencimiento SET studio_id = 1")
    op.alter_column("plantillas_vencimiento", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_plantillas_studio_id", "plantillas_vencimiento", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_plantillas_studio_id", "plantillas_vencimiento", ["studio_id"])

    # ── documentos ──────────────────────────────────────────────────────────────
    op.add_column("documentos", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE documentos SET studio_id = 1")
    op.alter_column("documentos", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_documentos_studio_id", "documentos", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_documentos_studio_id", "documentos", ["studio_id"])

    # ── automatizaciones (n8n) ──────────────────────────────────────────────────
    op.add_column("automatizaciones", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE automatizaciones SET studio_id = 1")
    op.alter_column("automatizaciones", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_automatizaciones_studio_id", "automatizaciones", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_automatizaciones_studio_id", "automatizaciones", ["studio_id"])

    # ── rentabilidad_mensual ─────────────────────────────────────────────────────
    op.add_column("rentabilidad_mensual", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE rentabilidad_mensual SET studio_id = 1")
    op.alter_column("rentabilidad_mensual", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_rentabilidad_studio_id", "rentabilidad_mensual", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_rentabilidad_studio_id", "rentabilidad_mensual", ["studio_id"])

    # ── sop_documentos ──────────────────────────────────────────────────────────
    op.add_column("sop_documentos", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE sop_documentos SET studio_id = 1")
    op.alter_column("sop_documentos", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_sop_documentos_studio_id", "sop_documentos", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_sop_documentos_studio_id", "sop_documentos", ["studio_id"])

    # ── gmail_config ────────────────────────────────────────────────────────────
    op.add_column("gmail_config", sa.Column("studio_id", sa.Integer(), nullable=True))
    op.execute("UPDATE gmail_config SET studio_id = 1")
    op.alter_column("gmail_config", "studio_id", nullable=False)
    op.create_foreign_key(
        "fk_gmail_config_studio_id", "gmail_config", "studios", ["studio_id"], ["id"]
    )
    op.create_index("ix_gmail_config_studio_id", "gmail_config", ["studio_id"])


def downgrade() -> None:
    op.drop_index("ix_gmail_config_studio_id", "gmail_config")
    op.drop_constraint("fk_gmail_config_studio_id", "gmail_config", type_="foreignkey")
    op.drop_column("gmail_config", "studio_id")

    op.drop_index("ix_sop_documentos_studio_id", "sop_documentos")
    op.drop_constraint("fk_sop_documentos_studio_id", "sop_documentos", type_="foreignkey")
    op.drop_column("sop_documentos", "studio_id")

    op.drop_index("ix_rentabilidad_studio_id", "rentabilidad_mensual")
    op.drop_constraint("fk_rentabilidad_studio_id", "rentabilidad_mensual", type_="foreignkey")
    op.drop_column("rentabilidad_mensual", "studio_id")

    op.drop_index("ix_automatizaciones_studio_id", "automatizaciones")
    op.drop_constraint("fk_automatizaciones_studio_id", "automatizaciones", type_="foreignkey")
    op.drop_column("automatizaciones", "studio_id")

    op.drop_index("ix_documentos_studio_id", "documentos")
    op.drop_constraint("fk_documentos_studio_id", "documentos", type_="foreignkey")
    op.drop_column("documentos", "studio_id")

    op.drop_index("ix_plantillas_studio_id", "plantillas_vencimiento")
    op.drop_constraint("fk_plantillas_studio_id", "plantillas_vencimiento", type_="foreignkey")
    op.drop_column("plantillas_vencimiento", "studio_id")

    op.drop_index("ix_automatizaciones_python_studio_id", "automatizaciones_python")
    op.drop_constraint("fk_automatizaciones_python_studio_id", "automatizaciones_python", type_="foreignkey")
    op.drop_column("automatizaciones_python", "studio_id")

    op.drop_index("ix_alertas_studio_id", "alertas_vencimiento")
    op.drop_constraint("fk_alertas_studio_id", "alertas_vencimiento", type_="foreignkey")
    op.drop_column("alertas_vencimiento", "studio_id")

    op.drop_index("ix_proceso_instancias_studio_id", "proceso_instancias")
    op.drop_constraint("fk_proceso_instancias_studio_id", "proceso_instancias", type_="foreignkey")
    op.drop_column("proceso_instancias", "studio_id")

    op.drop_index("ix_proceso_templates_studio_id", "proceso_templates")
    op.drop_constraint("fk_proceso_templates_studio_id", "proceso_templates", type_="foreignkey")
    op.drop_column("proceso_templates", "studio_id")

    op.drop_index("ix_tareas_studio_id", "tareas")
    op.drop_constraint("fk_tareas_studio_id", "tareas", type_="foreignkey")
    op.drop_column("tareas", "studio_id")

    op.drop_index("ix_vencimientos_studio_id", "vencimientos")
    op.drop_constraint("fk_vencimientos_studio_id", "vencimientos", type_="foreignkey")
    op.drop_column("vencimientos", "studio_id")

    op.drop_constraint("uq_clientes_cuit_studio", "clientes", type_="unique")
    op.create_unique_constraint("clientes_cuit_cuil_key", "clientes", ["cuit_cuil"])
    op.drop_index("ix_clientes_studio_id", "clientes")
    op.drop_constraint("fk_clientes_studio_id", "clientes", type_="foreignkey")
    op.drop_column("clientes", "studio_id")

    op.drop_constraint("uq_empleados_email_studio", "empleados", type_="unique")
    op.create_unique_constraint("empleados_email_key", "empleados", ["email"])
    op.drop_index("ix_empleados_studio_id", "empleados")
    op.drop_constraint("fk_empleados_studio_id", "empleados", type_="foreignkey")
    op.drop_column("empleados", "studio_id")

    op.drop_index("ix_usuarios_studio_id", "usuarios")
    op.drop_constraint("fk_usuarios_studio_id", "usuarios", type_="foreignkey")
    op.drop_column("usuarios", "studio_id")
