"""Specs: alertas, configuracion, onboarding, agentes, ficha cliente, portal

Revision ID: z7a8b9c0d1e2
Revises: y6z7a8b9c0d1
Create Date: 2026-04-16
"""
from alembic import op
import sqlalchemy as sa

revision = "z7a8b9c0d1e2"
down_revision = "y6z7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade():
    # ─── ALERTAS ──────────────────────────────────────────────────────────────
    # Nuevos campos en alertas_vencimiento
    with op.batch_alter_table("alertas_vencimiento") as batch_op:
        batch_op.add_column(sa.Column("tipo", sa.String(50), nullable=True, server_default="vencimiento"))
        # tipo: 'vencimiento' | 'mora' | 'riesgo' | 'tarea_vencida' | 'documentacion' | 'manual'
        batch_op.add_column(sa.Column("origen", sa.String(20), nullable=True, server_default="sistema"))
        # origen: 'sistema' | 'contador'
        batch_op.add_column(sa.Column("titulo", sa.String(300), nullable=True))
        batch_op.add_column(sa.Column("sent_via_portal", sa.Boolean(), nullable=True, server_default="false"))
        batch_op.add_column(sa.Column("portal_sent_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("ignorada_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("canal", sa.String(20), nullable=True))
        # canal: 'email' | 'portal' | 'ambos'
        batch_op.add_column(sa.Column("tipo_vencimiento_ref", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("tipo_documento_ref", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("documento_referencia", sa.String(300), nullable=True))
        batch_op.add_column(sa.Column("cobro_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("tarea_id", sa.Integer(), nullable=True))

    # ─── STUDIOS: ONBOARDING ──────────────────────────────────────────────────
    with op.batch_alter_table("studios") as batch_op:
        # Onboarding
        batch_op.add_column(sa.Column("onboarding_completado", sa.Boolean(), nullable=True, server_default="false"))
        batch_op.add_column(sa.Column("onboarding_paso_actual", sa.Integer(), nullable=True, server_default="1"))
        batch_op.add_column(sa.Column("estado_cuenta", sa.String(20), nullable=True, server_default="pendiente"))
        # estado_cuenta: 'pendiente' | 'activa' | 'suspendida'
        batch_op.add_column(sa.Column("telegram_configurado", sa.Boolean(), nullable=True, server_default="false"))
        batch_op.add_column(sa.Column("email_configurado", sa.Boolean(), nullable=True, server_default="false"))
        # Perfil del estudio (Configuración Sección 1)
        batch_op.add_column(sa.Column("cuit", sa.String(20), nullable=True))
        batch_op.add_column(sa.Column("razon_social", sa.String(300), nullable=True))
        batch_op.add_column(sa.Column("condicion_iva", sa.String(50), nullable=True, server_default="responsable_inscripto"))
        batch_op.add_column(sa.Column("direccion_fiscal", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("telefono_contacto", sa.String(50), nullable=True))
        batch_op.add_column(sa.Column("email_contacto", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("nombre_responsable", sa.String(255), nullable=True))
        batch_op.add_column(sa.Column("logo_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("provincia_principal", sa.String(100), nullable=True, server_default="Buenos Aires"))
        batch_op.add_column(sa.Column("tarifa_horaria_interna", sa.Numeric(10, 2), nullable=True, server_default="0"))
        # Facturación AFIP (Sección 2)
        batch_op.add_column(sa.Column("afip_certificado_path", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("afip_clave_privada_path", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("afip_punto_venta", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("afip_tipo_comprobante_default", sa.String(20), nullable=True, server_default="B"))
        batch_op.add_column(sa.Column("afip_modo", sa.String(20), nullable=True, server_default="homologacion"))
        # Cobranza (Sección 4)
        batch_op.add_column(sa.Column("cobro_dia_generacion", sa.Integer(), nullable=True, server_default="1"))
        batch_op.add_column(sa.Column("cobro_dias_gracia", sa.Integer(), nullable=True, server_default="3"))
        batch_op.add_column(sa.Column("cobro_metodo_default", sa.String(50), nullable=True, server_default="transferencia"))
        batch_op.add_column(sa.Column("cobro_banco", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("cobro_cbu_cvu", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("cobro_alias", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("cobro_titular_cuenta", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("cobro_mensaje_automatico", sa.Text(), nullable=True))
        # Notificaciones (Sección 6)
        batch_op.add_column(sa.Column("alerta_vencimiento_dias", sa.Integer(), nullable=True, server_default="7"))
        batch_op.add_column(sa.Column("alerta_documentacion_dias", sa.Integer(), nullable=True, server_default="5"))
        batch_op.add_column(sa.Column("alerta_cobro_gracia_dias", sa.Integer(), nullable=True, server_default="3"))
        batch_op.add_column(sa.Column("alerta_riesgo_umbral", sa.Integer(), nullable=True, server_default="70"))
        batch_op.add_column(sa.Column("notif_resumen_diario_telegram", sa.Boolean(), nullable=True, server_default="true"))
        batch_op.add_column(sa.Column("notif_resumen_semanal_email", sa.Boolean(), nullable=True, server_default="true"))
        batch_op.add_column(sa.Column("notif_criticas_email", sa.Boolean(), nullable=True, server_default="true"))
        batch_op.add_column(sa.Column("notif_criticas_telegram", sa.Boolean(), nullable=True, server_default="true"))
        batch_op.add_column(sa.Column("email_nombre_remitente", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("email_firma", sa.Text(), nullable=True))
        # Integraciones SMTP (Sección 8)
        batch_op.add_column(sa.Column("smtp_host", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("smtp_puerto", sa.Integer(), nullable=True, server_default="587"))
        batch_op.add_column(sa.Column("smtp_usuario", sa.String(200), nullable=True))
        batch_op.add_column(sa.Column("smtp_password_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("smtp_usar_tls", sa.Boolean(), nullable=True, server_default="true"))
        batch_op.add_column(sa.Column("smtp_verificado", sa.Boolean(), nullable=True, server_default="false"))
        batch_op.add_column(sa.Column("email_notificaciones", sa.String(200), nullable=True))
        # Portal del cliente (Sección 9)
        batch_op.add_column(sa.Column("portal_habilitado", sa.Boolean(), nullable=True, server_default="false"))
        batch_op.add_column(sa.Column("portal_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("portal_texto_bienvenida", sa.Text(), nullable=True))
        # Sistema (Sección 11)
        batch_op.add_column(sa.Column("claude_api_key_encrypted", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("claude_modelo", sa.String(100), nullable=True, server_default="claude-sonnet-4-6"))
        batch_op.add_column(sa.Column("debug_mode", sa.Boolean(), nullable=True, server_default="false"))
        # Usuario de portal auth (para clientes)
        batch_op.add_column(sa.Column("password_hash", sa.String(255), nullable=True))

    # ─── CLIENTES: nuevos campos ───────────────────────────────────────────────
    # notas ya existe desde migración y6z7a8b9c0d1 — solo agregar requiere_categoria
    with op.batch_alter_table("clientes") as batch_op:
        batch_op.add_column(sa.Column("requiere_categoria", sa.Boolean(), nullable=True, server_default="false"))

    # ─── CONFIG_HONORARIOS ────────────────────────────────────────────────────
    op.create_table(
        "config_honorarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False, unique=True),
        sa.Column("honorario_monotributista", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("honorario_responsable_inscripto", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("honorario_sociedad", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("honorario_empleador_adicional", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("honorario_otro", sa.Numeric(12, 2), nullable=True, server_default="0"),
        sa.Column("ajuste_inflacion_activo", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("ajuste_inflacion_porcentaje", sa.Numeric(5, 2), nullable=True, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_config_honorarios_studio_id", "config_honorarios", ["studio_id"])

    # ─── CONFIG_CALENDARIO ────────────────────────────────────────────────────
    op.create_table(
        "config_calendario",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False, unique=True),
        sa.Column("iibb_provincia", sa.String(100), nullable=True, server_default="CABA"),
        sa.Column("iibb_dia_vencimiento", sa.Integer(), nullable=True, server_default="15"),
        sa.Column("bienes_personales_mes", sa.Integer(), nullable=True, server_default="6"),
        sa.Column("bienes_personales_dia", sa.Integer(), nullable=True, server_default="20"),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_config_calendario_studio_id", "config_calendario", ["studio_id"])

    # ─── VENCIMIENTOS_SUGERIDOS ───────────────────────────────────────────────
    op.create_table(
        "vencimientos_sugeridos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("tipo_obligacion", sa.String(100), nullable=False),
        sa.Column("periodo", sa.String(20), nullable=False),
        sa.Column("fecha_vencimiento_estimada", sa.Date(), nullable=False),
        sa.Column("fecha_es_estimada", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("nota_verificacion", sa.Text(), nullable=True),
        sa.Column("estado", sa.String(30), nullable=True, server_default="pendiente_confirmacion"),
        # estado: 'pendiente_confirmacion' | 'confirmado' | 'descartado'
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_vencimientos_sugeridos_studio_id", "vencimientos_sugeridos", ["studio_id"])
    op.create_index("ix_vencimientos_sugeridos_cliente_id", "vencimientos_sugeridos", ["cliente_id"])

    # ─── PORTAL_USUARIOS (clientes con acceso JWT al portal) ─────────────────
    op.create_table(
        "portal_usuarios",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=True, server_default="true"),
        sa.Column("ultimo_acceso", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_portal_usuarios_studio_id", "portal_usuarios", ["studio_id"])
    op.create_index("ix_portal_usuarios_email", "portal_usuarios", ["email"])

    # ─── PORTAL_NOTIFICACIONES ────────────────────────────────────────────────
    op.create_table(
        "portal_notificaciones",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False),
        sa.Column("cliente_id", sa.Integer(), sa.ForeignKey("clientes.id"), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=True, server_default="alerta_manual"),
        # tipo: 'alerta_manual' | 'vencimiento' | 'documento' | 'cobro'
        sa.Column("titulo", sa.String(300), nullable=False),
        sa.Column("mensaje", sa.Text(), nullable=False),
        sa.Column("leida", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("leida_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_portal_notificaciones_cliente_id", "portal_notificaciones", ["cliente_id"])
    op.create_index("ix_portal_notificaciones_studio_id", "portal_notificaciones", ["studio_id"])

    # ─── ONBOARDING_PASOS ─────────────────────────────────────────────────────
    op.create_table(
        "onboarding_pasos",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("studio_id", sa.Integer(), sa.ForeignKey("studios.id"), nullable=False, unique=True),
        sa.Column("paso1_completado", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("paso2_completado", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("paso3_completado", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("paso4_completado", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("paso5_completado", sa.Boolean(), nullable=True, server_default="false"),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_onboarding_pasos_studio_id", "onboarding_pasos", ["studio_id"])


def downgrade():
    op.drop_table("onboarding_pasos")
    op.drop_table("portal_notificaciones")
    op.drop_table("portal_usuarios")
    op.drop_table("vencimientos_sugeridos")
    op.drop_table("config_calendario")
    op.drop_table("config_honorarios")

    with op.batch_alter_table("clientes") as batch_op:
        batch_op.drop_column("requiere_categoria")

    with op.batch_alter_table("studios") as batch_op:
        for col in [
            "debug_mode", "claude_modelo", "claude_api_key_encrypted",
            "portal_texto_bienvenida", "portal_url", "portal_habilitado",
            "email_notificaciones", "smtp_verificado", "smtp_usar_tls",
            "smtp_password_encrypted", "smtp_usuario", "smtp_puerto", "smtp_host",
            "email_firma", "email_nombre_remitente",
            "notif_criticas_telegram", "notif_criticas_email",
            "notif_resumen_semanal_email", "notif_resumen_diario_telegram",
            "alerta_riesgo_umbral", "alerta_cobro_gracia_dias",
            "alerta_documentacion_dias", "alerta_vencimiento_dias",
            "cobro_mensaje_automatico", "cobro_titular_cuenta", "cobro_alias",
            "cobro_cbu_cvu", "cobro_banco", "cobro_metodo_default",
            "cobro_dias_gracia", "cobro_dia_generacion",
            "afip_modo", "afip_tipo_comprobante_default", "afip_punto_venta",
            "afip_clave_privada_path", "afip_certificado_path",
            "tarifa_horaria_interna", "provincia_principal", "logo_url",
            "nombre_responsable", "email_contacto", "telefono_contacto",
            "direccion_fiscal", "condicion_iva", "razon_social", "cuit",
            "email_configurado", "telegram_configurado",
            "estado_cuenta", "onboarding_paso_actual", "onboarding_completado",
            "password_hash",
        ]:
            batch_op.drop_column(col)

    with op.batch_alter_table("alertas_vencimiento") as batch_op:
        for col in [
            "tarea_id", "cobro_id", "documento_referencia",
            "tipo_documento_ref", "tipo_vencimiento_ref", "canal",
            "ignorada_at", "portal_sent_at", "sent_via_portal",
            "titulo", "origen", "tipo",
        ]:
            batch_op.drop_column(col)
