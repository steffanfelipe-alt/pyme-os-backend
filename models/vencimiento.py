import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TipoVencimiento(str, enum.Enum):
    iva = "iva"
    ddjj_anual = "ddjj_anual"
    monotributo = "monotributo"
    iibb = "iibb"
    ganancias = "ganancias"
    bienes_personales = "bienes_personales"
    autonomos = "autonomos"
    sueldos_cargas = "sueldos_cargas"
    otro = "otro"


class EstadoVencimiento(str, enum.Enum):
    pendiente = "pendiente"
    cumplido = "cumplido"
    vencido = "vencido"


class Vencimiento(Base):
    __tablename__ = "vencimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False)
    tipo: Mapped[TipoVencimiento] = mapped_column(Enum(TipoVencimiento), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(255), nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_cumplimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[EstadoVencimiento] = mapped_column(
        Enum(EstadoVencimiento), default=EstadoVencimiento.pendiente, nullable=False
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
