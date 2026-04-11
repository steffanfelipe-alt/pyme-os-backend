from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class AsistenteCanal(Base):
    """Mapea cada usuario (empleado o cliente) a su identificador en un canal."""
    __tablename__ = "asistente_canales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("studios.id"), nullable=True
    )
    tipo_usuario: Mapped[str] = mapped_column(String(10), nullable=False)  # "empleado" | "cliente"
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    canal: Mapped[str] = mapped_column(String(10), nullable=False)  # "telegram" | "email"
    # telegram_user_id numérico o dirección de email del cliente
    identificador: Mapped[str] = mapped_column(String(255), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AsistenteMensaje(Base):
    """Log de auditoría de todos los mensajes del asistente."""
    __tablename__ = "asistente_mensajes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("studios.id"), nullable=True
    )
    tipo_usuario: Mapped[str] = mapped_column(String(10), nullable=False)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    canal: Mapped[str] = mapped_column(String(10), nullable=False)
    direccion: Mapped[str] = mapped_column(String(10), nullable=False)  # "entrante" | "saliente"
    contenido_raw: Mapped[str] = mapped_column(Text, nullable=False)
    contenido_procesado: Mapped[str | None] = mapped_column(Text, nullable=True)
    intencion_detectada: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entidades_extraidas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    estado: Mapped[str] = mapped_column(
        String(30), default="procesado", nullable=False
    )  # "procesado" | "fallido" | "requiere_confirmacion"
    error_detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AsistenteConfirmacionPendiente(Base):
    """Operaciones de escritura en espera de confirmación explícita del usuario."""
    __tablename__ = "asistente_confirmaciones_pendientes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    canal: Mapped[str] = mapped_column(String(10), nullable=False)
    operacion: Mapped[dict] = mapped_column(JSON, nullable=False)
    expira_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # null = pendiente, True = confirmado, False = cancelado
    confirmado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class AsistenteSesionWizard(Base):
    """Estado de un wizard conversacional multi-paso en Telegram."""
    __tablename__ = "asistente_sesiones_wizard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    comando: Mapped[str] = mapped_column(String(20), nullable=False)  # "task" | "cliente"
    paso_actual: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    datos_parciales: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    expira_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
