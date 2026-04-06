from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class RentabilidadMensual(Base):
    __tablename__ = "rentabilidad_mensual"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("clientes.id"), nullable=False
    )
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    honorario: Mapped[float] = mapped_column(Float, nullable=False)
    horas_reales: Mapped[float] = mapped_column(Float, nullable=False)
    horas_estimadas: Mapped[float | None] = mapped_column(Float, nullable=True)
    rentabilidad_hora: Mapped[float | None] = mapped_column(Float, nullable=True)
    tareas_completadas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tareas_demoradas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    costo_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    profit_margin_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
