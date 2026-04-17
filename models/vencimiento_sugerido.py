from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class VencimientoSugerido(Base):
    __tablename__ = "vencimientos_sugeridos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    cliente_id: Mapped[int] = mapped_column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    # ej: 'IVA', 'Ganancias', 'Monotributo', 'IIBB', 'F931', 'Bienes Personales'
    tipo_obligacion: Mapped[str] = mapped_column(String(100), nullable=False)
    # formato YYYY-MM
    periodo: Mapped[str] = mapped_column(String(20), nullable=False)
    fecha_vencimiento_estimada: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_es_estimada: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nota_verificacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 'pendiente_confirmacion' | 'confirmado' | 'descartado'
    estado: Mapped[str] = mapped_column(String(30), default="pendiente_confirmacion", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
