import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class TipoTarea(str, enum.Enum):
    tarea = "tarea"
    requerimiento = "requerimiento"
    declaracion = "declaracion"
    conciliacion = "conciliacion"
    auditoria = "auditoria"
    asesoramiento = "asesoramiento"
    otro = "otro"


class PrioridadTarea(str, enum.Enum):
    baja = "baja"
    media = "media"
    normal = "normal"
    alta = "alta"
    urgente = "urgente"


class EstadoTarea(str, enum.Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completada = "completada"


class Tarea(Base):
    __tablename__ = "tareas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=True)
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
    horas_estimadas: Mapped[float | None] = mapped_column(Float, nullable=True)
    horas_reales: Mapped[float | None] = mapped_column(Float, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # FK nullable — vincula la tarea a un paso específico de una instancia de proceso
    proceso_instancia_paso_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proceso_pasos_instancia.id"), nullable=True
    )

    sesiones = relationship("TareaSesion", back_populates="tarea", cascade="all, delete-orphan")

    cliente = relationship("Cliente", foreign_keys=[cliente_id], lazy="joined")
    empleado_rel = relationship("Empleado", foreign_keys=[empleado_id], lazy="joined")

    @property
    def cliente_nombre(self) -> str | None:
        if self.cliente is None:
            return None
        return getattr(self.cliente, "nombre", None)

    @property
    def empleado_nombre(self) -> str | None:
        if self.empleado_rel is None:
            return None
        return getattr(self.empleado_rel, "nombre", None)
