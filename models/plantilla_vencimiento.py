import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.cliente import CondicionFiscal
from models.vencimiento import TipoVencimiento


class RecurrenciaPlantilla(str, enum.Enum):
    mensual = "mensual"
    bimestral = "bimestral"
    cuatrimestral = "cuatrimestral"
    anual = "anual"


class PlantillaVencimiento(Base):
    __tablename__ = "plantillas_vencimiento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    studio_id: Mapped[int] = mapped_column(Integer, ForeignKey("studios.id"), nullable=False, index=True)
    condicion_fiscal: Mapped[CondicionFiscal] = mapped_column(Enum(CondicionFiscal), nullable=False)
    tipo: Mapped[TipoVencimiento] = mapped_column(Enum(TipoVencimiento), nullable=False)
    descripcion_template: Mapped[str] = mapped_column(String(255), nullable=False)
    # Si mapa_digito_dia es None, se usa dia_vencimiento fijo
    # Si tiene valor: {"0": 7, "1": 7, "2": 8, ...} → el admin puede configurarlo
    dia_vencimiento: Mapped[int] = mapped_column(Integer, nullable=False)
    mapa_digito_dia: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    recurrencia: Mapped[RecurrenciaPlantilla] = mapped_column(
        Enum(RecurrenciaPlantilla), nullable=False
    )
    mes_inicio: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Para anual: mes (1-12)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
