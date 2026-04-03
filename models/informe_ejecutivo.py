from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class InformeEjecutivo(Base):
    __tablename__ = "informes_ejecutivos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    periodo: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    generado_por_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("usuarios.id"), nullable=True
    )

    resumen_vencimientos: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resumen_workload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resumen_rentabilidad: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resumen_alertas: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resumen_riesgo: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    total_clientes_activos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    alertas_criticas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clientes_riesgo_rojo: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
