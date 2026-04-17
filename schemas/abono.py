from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.abono import EstadoCobro, PeriodicidadAbono


class AbonoCreate(BaseModel):
    cliente_id: int
    concepto: str
    monto: float
    periodicidad: PeriodicidadAbono = PeriodicidadAbono.mensual
    fecha_inicio: date
    activo: bool = True
    notas: Optional[str] = None


class AbonoUpdate(BaseModel):
    concepto: Optional[str] = None
    monto: Optional[float] = None
    periodicidad: Optional[PeriodicidadAbono] = None
    fecha_proximo_cobro: Optional[date] = None
    activo: Optional[bool] = None
    notas: Optional[str] = None


class AbonoResponse(BaseModel):
    id: int
    studio_id: int
    cliente_id: int
    concepto: str
    monto: float
    periodicidad: PeriodicidadAbono
    fecha_inicio: date
    fecha_proximo_cobro: Optional[date]
    activo: bool
    notas: Optional[str]

    model_config = {"from_attributes": True}


class CobroResponse(BaseModel):
    id: int
    abono_id: int
    fecha_cobro: date
    monto: float
    estado: EstadoCobro
    notas: Optional[str]

    model_config = {"from_attributes": True}
