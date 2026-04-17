from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ConfigCalendario(Base):
    __tablename__ = "config_calendario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, unique=True, index=True)
    iibb_provincia: Mapped[str] = mapped_column(String(100), default="CABA", nullable=False)
    iibb_dia_vencimiento: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    bienes_personales_mes: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    bienes_personales_dia: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
