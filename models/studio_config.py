from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class StudioConfig(Base):
    """
    Configuración del estudio — singleton (solo existe un registro, id=1).
    Tabla creada automáticamente con valores por defecto si no existe.
    """
    __tablename__ = "studio_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Identidad del estudio
    nombre_estudio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_estudio: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Configuración operacional
    tarifa_hora_pesos: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    moneda: Mapped[str] = mapped_column(String(10), default="ARS", nullable=False)
    zona_horaria: Mapped[str] = mapped_column(
        String(50), default="America/Argentina/Buenos_Aires", nullable=False
    )
    # Umbral de instancias completadas requeridas antes de activar el optimizador.
    # Configurable por estudio; default 5.
    umbral_instancias_optimizador: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Días de anticipación para notificaciones de vencimientos. Default 7.
    umbral_dias_notificacion: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    # Campos para integración Telegram
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    telegram_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    telegram_connect_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    telegram_connect_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
