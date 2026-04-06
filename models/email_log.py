from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class EmailLog(Base):
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("studios.id"), nullable=True
    )
    recipient_type: Mapped[str] = mapped_column(String(10), nullable=False)  # "studio" | "client"
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="sent", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
