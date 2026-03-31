import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TipoTarea(str, enum.Enum):
    tarea = "tarea"
    requerimiento = "requerimiento"


class PrioridadTarea(str, enum.Enum):
    baja = "baja"
    media = "media"
    alta = "alta"


class EstadoTarea(str, enum.Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completada = "completada"


class Tarea(Base):
    __tablename__ = "tareas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False)
    empleado_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("empleados.id"), nullable=True
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[TipoTarea] = mapped_column(Enum(TipoTarea), nullable=False)
    prioridad: Mapped[PrioridadTarea] = mapped_column(
        Enum(PrioridadTarea), default=PrioridadTarea.media, nullable=False
    )
    estado: Mapped[EstadoTarea] = mapped_column(
        Enum(EstadoTarea), default=EstadoTarea.pendiente, nullable=False
    )
    fecha_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    fecha_completada: Mapped[date | None] = mapped_column(Date, nullable=True)
    tiempo_estimado: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tiempo_real: Mapped[int | None] = mapped_column(Integer, nullable=True)
    horas_estimadas: Mapped[float | None] = mapped_column(Float, nullable=True)
    horas_reales: Mapped[float | None] = mapped_column(Float, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
