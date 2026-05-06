"""
Modelos SQLAlchemy para el módulo de Facturación Electrónica (ARCA/AFIP).
"""
from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class Comprobante(Base):
    __tablename__ = "comprobantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("studios.id"), nullable=True, index=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False)

    tipo_comprobante: Mapped[str] = mapped_column(String(1), nullable=False)       # A, B, C
    punto_venta: Mapped[int] = mapped_column(Integer, nullable=False)
    numero_comprobante: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cae: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fecha_cae_vencimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)

    concepto: Mapped[int] = mapped_column(Integer, nullable=False, default=2)      # 2=Servicios
    descripcion_concepto: Mapped[str | None] = mapped_column(Text, nullable=True)

    importe_neto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    importe_iva: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    importe_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    alicuota_iva: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=21.0)

    # estado: pendiente / emitida / enviada / anulada
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    error_arca: Mapped[str | None] = mapped_column(Text, nullable=True)

    enviada_por_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enviada_por_telegram: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    pdf_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class HonorarioRecurrente(Base):
    __tablename__ = "honorarios_recurrentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("studios.id"), nullable=True, index=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False)

    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    importe_neto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    alicuota_iva: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=21.0)
    tipo_comprobante: Mapped[str] = mapped_column(String(1), nullable=False, default="B")
    dia_emision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ultimo_emitido: Mapped[date | None] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class PagoComprobante(Base):
    __tablename__ = "pagos_comprobantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("studios.id"), nullable=True, index=True)
    comprobante_id: Mapped[int] = mapped_column(Integer, ForeignKey("comprobantes.id"), nullable=False)

    fecha_pago: Mapped[date | None] = mapped_column(Date, nullable=True)
    medio_pago: Mapped[str | None] = mapped_column(String(50), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="pendiente")
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class StudioArcaConfig(Base):
    """Configuración ARCA por estudio: CUIT, punto de venta, certificados encriptados."""
    __tablename__ = "studio_arca_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    cuit: Mapped[str] = mapped_column(String(20), nullable=False)
    punto_venta: Mapped[int] = mapped_column(Integer, nullable=False)
    certificado_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    clave_privada_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    modo: Mapped[str] = mapped_column(String(20), nullable=False, default="homologacion")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
