from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AlertaVencimiento(Base):
    __tablename__ = "alertas_vencimiento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vencimiento_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("vencimientos.id"), nullable=False
    )
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False
    )
    nivel: Mapped[str] = mapped_column(String(15), nullable=False)  # critica | advertencia | informativa
    dias_restantes: Mapped[int] = mapped_column(Integer, nullable=False)
    documentos_faltantes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    vista: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    resuelta_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DocumentoRequerido(Base):
    __tablename__ = "documentos_requeridos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_vencimiento: Mapped[str] = mapped_column(String(50), nullable=False)
    tipo_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
