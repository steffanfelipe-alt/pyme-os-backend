import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TipoDocumento(str, enum.Enum):
    factura = "factura"
    liquidacion_sueldo = "liquidacion_sueldo"
    ddjj = "ddjj"
    recibo = "recibo"
    extracto_bancario = "extracto_bancario"
    balance = "balance"
    contrato = "contrato"
    otro = "otro"


class EstadoDocumento(str, enum.Enum):
    pendiente = "pendiente"
    procesado = "procesado"
    requiere_revision = "requiere_revision"
    error = "error"


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False)
    vencimiento_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("vencimientos.id"), nullable=True
    )
    nombre_original: Mapped[str] = mapped_column(String(255), nullable=False)
    ruta_archivo: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo_documento: Mapped[TipoDocumento] = mapped_column(
        Enum(TipoDocumento), default=TipoDocumento.otro, nullable=False
    )
    confianza: Mapped[float | None] = mapped_column(Float, nullable=True)
    resumen: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"periodo": "2026-03", "cuit_detectado": "20-...", "monto": 15000.0}
    metadatos: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    estado: Mapped[EstadoDocumento] = mapped_column(
        Enum(EstadoDocumento), default=EstadoDocumento.pendiente, nullable=False
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
