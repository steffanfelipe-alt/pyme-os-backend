from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel

from models.tarea import EstadoTarea, PrioridadTarea, TipoTarea


class TareaCreate(BaseModel):
    cliente_id: Optional[int] = None
    empleado_id: Optional[int] = None
    titulo: str
    descripcion: Optional[str] = None
    tipo: TipoTarea = TipoTarea.otro
    prioridad: PrioridadTarea = PrioridadTarea.normal
    fecha_limite: Optional[date] = None
    horas_estimadas: Optional[float] = None
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
    es_urgente: Optional[bool] = None
    es_importante: Optional[bool] = None


class PrioridadEisenhowerUpdate(BaseModel):
    es_urgente: bool
    es_importante: bool


class TareaResponse(BaseModel):
    id: int
    cliente_id: Optional[int]
    cliente_nombre: Optional[str] = None
    empleado_id: Optional[int]
    empleado_nombre: Optional[str] = None
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
    activo: bool
    es_urgente: bool = False
    es_importante: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CuadranteEisenhower(BaseModel):
    q1_urgente_importante: List[TareaResponse]
    q2_no_urgente_importante: List[TareaResponse]
    q3_urgente_no_importante: List[TareaResponse]
    q4_no_urgente_no_importante: List[TareaResponse]
    sin_clasificar: List[TareaResponse]
