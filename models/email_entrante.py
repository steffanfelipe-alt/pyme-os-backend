from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EmailEntrante(Base):
    __tablename__ = "emails_entrantes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Datos del email original
    remitente: Mapped[str] = mapped_column(String(255), nullable=False)
    asunto: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cuerpo_texto: Mapped[str | None] = mapped_column(Text, nullable=True)
    cuerpo_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    tiene_adjuntos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fecha_recibido: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    gmail_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True)

    # Clasificación automática
    categoria: Mapped[str | None] = mapped_column(String(50), nullable=True)
    urgencia: Mapped[str | None] = mapped_column(String(10), nullable=True)
    resumen: Mapped[str | None] = mapped_column(Text, nullable=True)
    remitente_tipo: Mapped[str | None] = mapped_column(String(30), nullable=True)
    confianza_clasificacion: Mapped[float | None] = mapped_column(Float, nullable=True)
    requiere_respuesta: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Revisión manual
    requiere_revision_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    motivo_revision: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Borrador de respuesta
    borrador_respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)
    borrador_aprobado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    borrador_editado: Mapped[str | None] = mapped_column(Text, nullable=True)
    respuesta_enviada_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Vinculaciones
    cliente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=True
    )
    asignado_a: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("empleados.id"), nullable=True
    )

    # Estado: no_leido | leido | respondido | archivado | spam
    estado: Mapped[str] = mapped_column(String(20), default="no_leido", nullable=False)
    leido_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
