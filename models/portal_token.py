import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PortalToken(Base):
    __tablename__ = "portal_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, default=lambda: uuid.uuid4().hex)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    expira_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
