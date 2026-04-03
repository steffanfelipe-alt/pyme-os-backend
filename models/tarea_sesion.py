from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class TareaSesion(Base):
    __tablename__ = "tarea_sesiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tarea_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tareas.id", ondelete="CASCADE"), nullable=False
    )
    empleado_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("empleados.id", ondelete="SET NULL"), nullable=True
    )
    inicio: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # calculado al cerrar: max(1, int((fin - inicio).total_seconds() // 60))
    minutos: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tarea = relationship("Tarea", back_populates="sesiones")
    empleado = relationship("Empleado")
