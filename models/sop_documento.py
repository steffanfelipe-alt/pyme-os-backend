import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AreaSop(str, enum.Enum):
    administracion = "administracion"
    impuestos = "impuestos"
    laboral = "laboral"
    atencion_cliente = "atencion_cliente"
    rrhh = "rrhh"
    otro = "otro"


class EstadoSop(str, enum.Enum):
    borrador = "borrador"
    activo = "activo"
    archivado = "archivado"


class SopDocumento(Base):
    __tablename__ = "sop_documentos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    area: Mapped[AreaSop] = mapped_column(Enum(AreaSop, native_enum=False), nullable=False)
    descripcion_proposito: Mapped[str | None] = mapped_column(Text, nullable=True)
    resultado_esperado: Mapped[str | None] = mapped_column(Text, nullable=True)
    empleado_creador_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("empleados.id"), nullable=True
    )
    empleado_responsable_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("empleados.id"), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fecha_ultima_revision: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    estado: Mapped[EstadoSop] = mapped_column(
        Enum(EstadoSop, native_enum=False), default=EstadoSop.borrador, nullable=False
    )
    proceso_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proceso_templates.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SopPaso(Base):
    __tablename__ = "sop_pasos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sop_id: Mapped[int] = mapped_column(Integer, ForeignKey("sop_documentos.id"), nullable=False)
    orden: Mapped[int] = mapped_column(Integer, nullable=False)
    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    responsable_sugerido: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tiempo_estimado_minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recursos: Mapped[str | None] = mapped_column(Text, nullable=True)
    es_automatizable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requiere_confirmacion_lectura: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SopRevision(Base):
    __tablename__ = "sop_revisiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sop_id: Mapped[int] = mapped_column(Integer, ForeignKey("sop_documentos.id"), nullable=False)
    fecha_revision: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    descripcion_cambio: Mapped[str | None] = mapped_column(Text, nullable=True)
    empleado_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("empleados.id"), nullable=True
    )
    version_resultante: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class SopConfirmacionLectura(Base):
    __tablename__ = "sop_confirmaciones_lectura"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sop_paso_id: Mapped[int] = mapped_column(Integer, ForeignKey("sop_pasos.id"), nullable=False)
    empleado_id: Mapped[int] = mapped_column(Integer, ForeignKey("empleados.id"), nullable=False)
    proceso_instancia_paso_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("proceso_pasos_instancia.id"), nullable=True
    )
    fecha_confirmacion: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
