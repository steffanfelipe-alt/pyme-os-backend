import enum
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TipoPersona(str, enum.Enum):
    fisica = "fisica"
    juridica = "juridica"


class CondicionFiscal(str, enum.Enum):
    responsable_inscripto = "responsable_inscripto"
    monotributista = "monotributista"
    exento = "exento"
    no_responsable = "no_responsable"
    relacion_de_dependencia = "relacion_de_dependencia"
    autonomos = "autonomos"
    sujeto_no_categorizado = "sujeto_no_categorizado"


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_persona: Mapped[TipoPersona] = mapped_column(Enum(TipoPersona), nullable=False)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    cuit_cuil: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telefono_whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email_notificaciones: Mapped[str | None] = mapped_column(String(255), nullable=True)
    acepta_notificaciones: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    condicion_fiscal: Mapped[CondicionFiscal] = mapped_column(Enum(CondicionFiscal), nullable=False)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    contador_asignado_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("empleados.id"), nullable=True
    )
    plantilla_aplicada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    honorarios_mensuales: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    satisfaccion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_baja: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(10), nullable=True)
    risk_calculated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    risk_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
