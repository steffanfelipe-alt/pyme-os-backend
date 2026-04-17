from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Studio(Base):
    __tablename__ = "studios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    # ── Onboarding ──────────────────────────────────────────────────────────
    onboarding_completado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    onboarding_paso_actual: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 'pendiente' | 'activa' | 'suspendida'
    estado_cuenta: Mapped[str] = mapped_column(String(20), default="pendiente", nullable=False)
    telegram_configurado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_configurado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Perfil del estudio (Configuración Sección 1) ─────────────────────────
    cuit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    razon_social: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # 'responsable_inscripto' | 'monotributista' | 'exento'
    condicion_iva: Mapped[str] = mapped_column(String(50), default="responsable_inscripto", nullable=False)
    direccion_fiscal: Mapped[str | None] = mapped_column(Text, nullable=True)
    telefono_contacto: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email_contacto: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nombre_responsable: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    provincia_principal: Mapped[str] = mapped_column(String(100), default="Buenos Aires", nullable=False)
    tarifa_horaria_interna: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0, nullable=False)

    # ── Facturación AFIP (Sección 2) ─────────────────────────────────────────
    afip_certificado_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    afip_clave_privada_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    afip_punto_venta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    afip_tipo_comprobante_default: Mapped[str] = mapped_column(String(20), default="B", nullable=False)
    # 'produccion' | 'homologacion'
    afip_modo: Mapped[str] = mapped_column(String(20), default="homologacion", nullable=False)

    # ── Cobranza (Sección 4) ─────────────────────────────────────────────────
    cobro_dia_generacion: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    cobro_dias_gracia: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    cobro_metodo_default: Mapped[str] = mapped_column(String(50), default="transferencia", nullable=False)
    cobro_banco: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cobro_cbu_cvu: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cobro_alias: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cobro_titular_cuenta: Mapped[str | None] = mapped_column(String(200), nullable=True)
    cobro_mensaje_automatico: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Notificaciones y alertas (Sección 6) ─────────────────────────────────
    alerta_vencimiento_dias: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    alerta_documentacion_dias: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    alerta_cobro_gracia_dias: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    alerta_riesgo_umbral: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    notif_resumen_diario_telegram: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notif_resumen_semanal_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notif_criticas_email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notif_criticas_telegram: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_nombre_remitente: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email_firma: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Integraciones SMTP (Sección 8) ───────────────────────────────────────
    smtp_host: Mapped[str | None] = mapped_column(String(200), nullable=True)
    smtp_puerto: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    smtp_usuario: Mapped[str | None] = mapped_column(String(200), nullable=True)
    smtp_password_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    smtp_usar_tls: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    smtp_verificado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    email_notificaciones: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # ── Portal del cliente (Sección 9) ───────────────────────────────────────
    portal_habilitado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    portal_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    portal_texto_bienvenida: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Sistema (Sección 11) ─────────────────────────────────────────────────
    claude_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    claude_modelo: Mapped[str] = mapped_column(String(100), default="claude-sonnet-4-6", nullable=False)
    debug_mode: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
