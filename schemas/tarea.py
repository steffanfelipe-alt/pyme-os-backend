from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.tarea import EstadoTarea, PrioridadTarea, TipoTarea


class TareaCreate(BaseModel):
    cliente_id: int
    empleado_id: Optional[int] = None
    titulo: str
    descripcion: Optional[str] = None
    tipo: TipoTarea
    prioridad: PrioridadTarea = PrioridadTarea.media
    fecha_limite: Optional[date] = None
    horas_estimadas: Optional[float] = None
    tiempo_estimado_min: Optional[int] = None
    notas: Optional[str] = None


class TareaUpdate(BaseModel):
    empleado_id: Optional[int] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[TipoTarea] = None
    prioridad: Optional[PrioridadTarea] = None
    estado: Optional[EstadoTarea] = None
    fecha_limite: Optional[date] = None
    fecha_completada: Optional[date] = None
    horas_estimadas: Optional[float] = None
    horas_reales: Optional[float] = None
    notas: Optional[str] = None
    activo: Optional[bool] = None


class TareaResponse(BaseModel):
    id: int
    cliente_id: int
    empleado_id: Optional[int]
    titulo: str
    descripcion: Optional[str]
    tipo: TipoTarea
    prioridad: PrioridadTarea
    estado: EstadoTarea
    fecha_limite: Optional[date]
    fecha_completada: Optional[date]
    horas_estimadas: Optional[float]
    horas_reales: Optional[float]
    notas: Optional[str]
    tiempo_estimado_min: Optional[int]
    tiempo_real_min: int
    activo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
