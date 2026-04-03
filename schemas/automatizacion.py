from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from models.proceso import EstadoAutomatizacion


class AutomatizacionAnalisisRequest(BaseModel):
    template_id: int


class GenerarFlujoRequest(BaseModel):
    template_id: int


class AutomatizacionUpdate(BaseModel):
    estado: Optional[EstadoAutomatizacion] = None
    ahorro_horas_mes: Optional[float] = None


class AutomatizacionResponse(BaseModel):
    id: int
    template_id: int
    flujo_json: Optional[dict[str, Any]]
    analisis_pasos: Optional[dict[str, Any]]
    ahorro_horas_mes: float
    herramienta: str
    estado: EstadoAutomatizacion
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerarFlujoResponse(BaseModel):
    automatizacion: AutomatizacionResponse
    requiere_revision: bool = True
    mensaje: str = "El flujo fue generado. Revisá los nodos antes de importar a n8n."
