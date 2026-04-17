from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class GmailConfig(Base):
    __tablename__ = "gmail_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    # Un estudio = un Gmail conectado (unique)
    studio_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    gmail_address: Mapped[str] = mapped_column(String(255), nullable=False)

    # Tokens encriptados con Fernet — NUNCA en texto plano
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Gmail watch expira cada 7 días — renovar con APScheduler
    watch_expiry: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    watch_history_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
