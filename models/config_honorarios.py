from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ConfigHonorarios(Base):
    __tablename__ = "config_honorarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, unique=True, index=True)
    honorario_monotributista: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    honorario_responsable_inscripto: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    honorario_sociedad: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    honorario_empleador_adicional: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    honorario_otro: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    ajuste_inflacion_activo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ajuste_inflacion_porcentaje: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
