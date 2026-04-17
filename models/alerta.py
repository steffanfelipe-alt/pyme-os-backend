from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AlertaVencimiento(Base):
    __tablename__ = "alertas_vencimiento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    vencimiento_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("vencimientos.id"), nullable=True
    )
    cliente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=True
    )
    # tipo: 'vencimiento' | 'mora' | 'riesgo' | 'tarea_vencida' | 'documentacion' | 'manual'
    tipo: Mapped[str] = mapped_column(String(50), nullable=False, default="vencimiento")
    # origen: 'sistema' | 'contador'
    origen: Mapped[str] = mapped_column(String(20), nullable=False, default="sistema")
    titulo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    nivel: Mapped[str] = mapped_column(String(15), nullable=False)  # critica | advertencia | informativa
    dias_restantes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    documentos_faltantes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    mensaje: Mapped[str] = mapped_column(Text, nullable=False)
    vista: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_via_telegram: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_via_email: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_via_portal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    portal_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # canal de envío para alertas manuales: 'email' | 'portal' | 'ambos'
    canal: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tipo_vencimiento_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tipo_documento_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    documento_referencia: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cobro_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tarea_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    resuelta_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ignorada_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class DocumentoRequerido(Base):
    __tablename__ = "documentos_requeridos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tipo_vencimiento: Mapped[str] = mapped_column(String(50), nullable=False)
    tipo_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(200), nullable=True)
