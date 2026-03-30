from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models.cliente import CondicionFiscal
from models.plantilla_vencimiento import RecurrenciaPlantilla
from models.vencimiento import TipoVencimiento


class PlantillaCreate(BaseModel):
    condicion_fiscal: CondicionFiscal
    tipo: TipoVencimiento
    descripcion_template: str
    dia_vencimiento: int
    mapa_digito_dia: Optional[dict] = None
    recurrencia: RecurrenciaPlantilla
    mes_inicio: Optional[int] = None


class PlantillaUpdate(BaseModel):
    descripcion_template: Optional[str] = None
    dia_vencimiento: Optional[int] = None
    mapa_digito_dia: Optional[dict] = None
    recurrencia: Optional[RecurrenciaPlantilla] = None
    mes_inicio: Optional[int] = None
    activo: Optional[bool] = None


class PlantillaResponse(BaseModel):
    id: int
    condicion_fiscal: CondicionFiscal
    tipo: TipoVencimiento
    descripcion_template: str
    dia_vencimiento: int
    mapa_digito_dia: Optional[dict]
    recurrencia: RecurrenciaPlantilla
    mes_inicio: Optional[int]
    activo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
