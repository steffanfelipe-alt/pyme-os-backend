from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, computed_field

from models.vencimiento import EstadoVencimiento, TipoVencimiento


class VencimientoCreate(BaseModel):
    cliente_id: int
    tipo: TipoVencimiento
    descripcion: str
    fecha_vencimiento: date
    notas: Optional[str] = None


class VencimientoUpdate(BaseModel):
    tipo: Optional[TipoVencimiento] = None
    descripcion: Optional[str] = None
    fecha_vencimiento: Optional[date] = None
    fecha_cumplimiento: Optional[date] = None
    estado: Optional[EstadoVencimiento] = None
    notas: Optional[str] = None


class VencimientoResponse(BaseModel):
    id: int
    cliente_id: int
    tipo: TipoVencimiento
    descripcion: str
    fecha_vencimiento: date
    fecha_cumplimiento: Optional[date]
    estado: EstadoVencimiento
    notas: Optional[str]
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def dias_para_vencer(self) -> int:
        return (self.fecha_vencimiento - date.today()).days

    model_config = {"from_attributes": True}
