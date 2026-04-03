from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from models.sop_documento import AreaSop, EstadoSop


# ─── SopPaso ──────────────────────────────────────────────────────────────────

class SopPasoCreate(BaseModel):
    orden: int
    descripcion: str
    responsable_sugerido: Optional[str] = None
    tiempo_estimado_minutos: Optional[int] = None
    recursos: Optional[str] = None
    es_automatizable: bool = False
    requiere_confirmacion_lectura: bool = False


class SopPasoResponse(BaseModel):
    id: int
    sop_id: int
    orden: int
    descripcion: str
    responsable_sugerido: Optional[str]
    tiempo_estimado_minutos: Optional[int]
    recursos: Optional[str]
    es_automatizable: bool
    requiere_confirmacion_lectura: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── SopRevision ─────────────────────────────────────────────────────────────

class SopRevisionResponse(BaseModel):
    id: int
    sop_id: int
    fecha_revision: datetime
    descripcion_cambio: Optional[str]
    empleado_id: Optional[int]
    version_resultante: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── SopDocumento ─────────────────────────────────────────────────────────────

class SopDocumentoCreate(BaseModel):
    titulo: str
    area: AreaSop = AreaSop.otro
    descripcion_proposito: Optional[str] = None
    resultado_esperado: Optional[str] = None
    empleado_responsable_id: Optional[int] = None
    proceso_id: Optional[int] = None
    pasos: list[SopPasoCreate] = []


class SopDocumentoUpdate(BaseModel):
    titulo: Optional[str] = None
    area: Optional[AreaSop] = None
    descripcion_proposito: Optional[str] = None
    resultado_esperado: Optional[str] = None
    empleado_responsable_id: Optional[int] = None
    proceso_id: Optional[int] = None


class SopDocumentoResponse(BaseModel):
    id: int
    titulo: str
    area: AreaSop
    descripcion_proposito: Optional[str]
    resultado_esperado: Optional[str]
    empleado_creador_id: Optional[int]
    empleado_responsable_id: Optional[int]
    version: int
    fecha_ultima_revision: Optional[datetime]
    estado: EstadoSop
    proceso_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    pasos: list[SopPasoResponse] = []
    revisiones: list[SopRevisionResponse] = []

    model_config = {"from_attributes": True}


# ─── Generación asistida ──────────────────────────────────────────────────────

class GenerarSopRequest(BaseModel):
    descripcion: str
    area: Optional[AreaSop] = None


# ─── Biblioteca ───────────────────────────────────────────────────────────────

class ProcesoVinculadoInfo(BaseModel):
    id: int
    nombre: str


class SopBibliotecaItem(BaseModel):
    id: int
    titulo: str
    area: AreaSop
    descripcion_proposito: Optional[str]
    resultado_esperado: Optional[str]
    responsable_nombre: Optional[str]
    fecha_ultima_revision: Optional[datetime]
    cantidad_pasos: int
    pasos: list[SopPasoResponse] = []
    proceso_vinculado: Optional[ProcesoVinculadoInfo]


# ─── Confirmación de lectura ──────────────────────────────────────────────────

class ConfirmarLecturaResponse(BaseModel):
    confirmado: bool
    mensaje: str
    requiere_confirmacion: bool
