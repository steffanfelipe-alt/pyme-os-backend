from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class StudioConfig(Base):
    """
    Configuración del estudio — singleton (solo existe un registro, id=1).
    Tabla creada automáticamente con valores por defecto si no existe.
    """
    __tablename__ = "studio_config"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tarifa_hora_pesos: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    moneda: Mapped[str] = mapped_column(String(10), default="ARS", nullable=False)
    zona_horaria: Mapped[str] = mapped_column(
        String(50), default="America/Argentina/Buenos_Aires", nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
