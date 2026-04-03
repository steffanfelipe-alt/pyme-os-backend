import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text, UniqueConstraint, func, JSON,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class TipoProceso(str, enum.Enum):
    onboarding = "onboarding"
    liquidacion_iva = "liquidacion_iva"
    balance = "balance"
    cierre_ejercicio = "cierre_ejercicio"
    declaracion_ganancias = "declaracion_ganancias"
    declaracion_iibb = "declaracion_iibb"
    otro = "otro"


class EstadoInstancia(str, enum.Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completado = "completado"
    cancelado = "cancelado"


class EstadoPasoInstancia(str, enum.Enum):
    pendiente = "pendiente"
    en_progreso = "en_progreso"
    completado = "completado"


class EstadoAutomatizacion(str, enum.Enum):
    borrador = "borrador"
    activa = "activa"
    pausada = "pausada"


class ProcesoTemplate(Base):
    __tablename__ = "proceso_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tipo: Mapped[TipoProceso] = mapped_column(Enum(TipoProceso), nullable=False)
    tiempo_estimado_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sop_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sop_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    creado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("empleados.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProcesoPasoTemplate(Base):
    __tablename__ = "proceso_pasos_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("proceso_templates.id"), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    tiempo_estimado_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    es_automatizable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (UniqueConstraint("template_id", "orden", name="uq_template_orden"),)


class ProcesoInstancia(Base):
    __tablename__ = "proceso_instancias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("proceso_templates.id"), nullable=False)
    cliente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=True)
    vencimiento_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("vencimientos.id"), nullable=True)
    estado: Mapped[EstadoInstancia] = mapped_column(
        Enum(EstadoInstancia), default=EstadoInstancia.pendiente, nullable=False
    )
    progreso_pct: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    fecha_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    creado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("empleados.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ProcesoPasoInstancia(Base):
    __tablename__ = "proceso_pasos_instancia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instancia_id: Mapped[int] = mapped_column(Integer, ForeignKey("proceso_instancias.id"), nullable=False)
    paso_template_id: Mapped[int] = mapped_column(Integer, ForeignKey("proceso_pasos_template.id"), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[EstadoPasoInstancia] = mapped_column(
        Enum(EstadoPasoInstancia), default=EstadoPasoInstancia.pendiente, nullable=False
    )
    fecha_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tiempo_real_minutos: Mapped[float | None] = mapped_column(Float, nullable=True)
    notas: Mapped[str | None] = mapped_column(Text, nullable=True)
    asignado_a: Mapped[int | None] = mapped_column(Integer, ForeignKey("empleados.id"), nullable=True)


class Automatizacion(Base):
    __tablename__ = "automatizaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(Integer, ForeignKey("proceso_templates.id"), unique=True, nullable=False)
    flujo_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analisis_pasos: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ahorro_horas_mes: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    herramienta: Mapped[str] = mapped_column(String(50), default="n8n", nullable=False)
    estado: Mapped[EstadoAutomatizacion] = mapped_column(
        Enum(EstadoAutomatizacion), default=EstadoAutomatizacion.borrador, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
