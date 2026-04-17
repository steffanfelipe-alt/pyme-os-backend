import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class PeriodicidadAbono(str, enum.Enum):
    mensual = "mensual"
    bimestral = "bimestral"
    trimestral = "trimestral"
    semestral = "semestral"
    anual = "anual"


class EstadoCobro(str, enum.Enum):
    pendiente = "pendiente"
    cobrado = "cobrado"
    vencido = "vencido"


class Abono(Base):
    __tablename__ = "abonos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    periodicidad: Mapped[PeriodicidadAbono] = mapped_column(
        Enum(PeriodicidadAbono), default=PeriodicidadAbono.mensual, nullable=False
    )
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_proximo_cobro: Mapped[date | None] = mapped_column(Date, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    cobros = relationship("Cobro", back_populates="abono", cascade="all, delete-orphan")


class Cobro(Base):
    __tablename__ = "cobros"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    abono_id: Mapped[int] = mapped_column(Integer, ForeignKey("abonos.id"), nullable=False, index=True)
    fecha_cobro: Mapped[date] = mapped_column(Date, nullable=False)
    monto: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    estado: Mapped[EstadoCobro] = mapped_column(
        Enum(EstadoCobro), default=EstadoCobro.pendiente, nullable=False
    )
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    abono = relationship("Abono", back_populates="cobros")
