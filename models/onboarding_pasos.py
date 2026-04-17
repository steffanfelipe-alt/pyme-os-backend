from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class OnboardingPasos(Base):
    __tablename__ = "onboarding_pasos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, unique=True, index=True)
    paso1_completado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paso2_completado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paso3_completado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paso4_completado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paso5_completado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
