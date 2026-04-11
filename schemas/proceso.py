from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models.proceso import EstadoInstancia, EstadoPasoInstancia, TipoProceso


# --- ProcesoPasoTemplate ---

class ProcesoPasoTemplateCreate(BaseModel):
    orden: int
    titulo: str
    descripcion: Optional[str] = None
    tiempo_estimado_minutos: Optional[int] = None
    es_automatizable: bool = False


class ProcesoPasoTemplateUpdate(BaseModel):
    orden: Optional[int] = None
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    tiempo_estimado_minutos: Optional[int] = None
    es_automatizable: Optional[bool] = None


class ProcesoPasoTemplateResponse(BaseModel):
    id: int
    template_id: int
    orden: int
    titulo: str
    descripcion: Optional[str]
    tiempo_estimado_minutos: Optional[int]
    es_automatizable: bool

    model_config = {"from_attributes": True}


# --- ProcesoTemplate ---

class ProcesoTemplateCreate(BaseModel):
    nombre: str
    descripcion: Optional[str] = None
    tipo: TipoProceso


class ProcesoTemplateUpdate(BaseModel):
    nombre: Optional[str] = None
    descripcion: Optional[str] = None
    tipo: Optional[TipoProceso] = None
    activo: Optional[bool] = None


class ProcesoTemplateResponse(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    tipo: TipoProceso
    tiempo_estimado_minutos: Optional[int]
    sop_url: Optional[str]
    sop_version: int
    sop_generado: bool
    activo: bool
    creado_por: Optional[int]
    created_at: datetime
    updated_at: datetime
    pasos: list[ProcesoPasoTemplateResponse] = []
    tiene_version_anterior: bool = False

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_pasos(cls, template, pasos: list):
        return cls(
            id=template.id,
            nombre=template.nombre,
            descripcion=template.descripcion,
            tipo=template.tipo,
            tiempo_estimado_minutos=template.tiempo_estimado_minutos,
            sop_url=template.sop_url,
            sop_version=template.sop_version,
            sop_generado=template.sop_url is not None,
            activo=template.activo,
            creado_por=template.creado_por,
            created_at=template.created_at,
            updated_at=template.updated_at,
            pasos=[ProcesoPasoTemplateResponse.model_validate(p) for p in pasos],
            tiene_version_anterior=bool(getattr(template, "version_anterior_json", None)),
        )


# --- ProcesoPasoInstancia ---

class ProcesoPasoInstanciaUpdate(BaseModel):
    estado: Optional[EstadoPasoInstancia] = None
    notas: Optional[str] = None
    asignado_a: Optional[int] = None


class ProcesoPasoInstanciaResponse(BaseModel):
    id: int
    instancia_id: int
    paso_template_id: int
    orden: int
    estado: EstadoPasoInstancia
    fecha_inicio: Optional[datetime]
    fecha_fin: Optional[datetime]
    tiempo_real_minutos: Optional[float]
    notas: Optional[str]
    asignado_a: Optional[int]
    guia_sop: Optional[str] = None

    model_config = {"from_attributes": True}


# --- ProcesoInstancia ---

class ProcesoInstanciaCreate(BaseModel):
    template_id: int
    cliente_id: Optional[int] = None
    vencimiento_id: Optional[int] = None


class ProcesoInstanciaUpdate(BaseModel):
    estado: Optional[EstadoInstancia] = None


class ProcesoInstanciaResponse(BaseModel):
    id: int
    template_id: int
    cliente_id: Optional[int]
    vencimiento_id: Optional[int]
    estado: EstadoInstancia
    progreso_pct: float
    fecha_inicio: Optional[datetime]
    fecha_fin: Optional[datetime]
    creado_por: Optional[int]
    created_at: datetime
    updated_at: datetime
    pasos: list[ProcesoPasoInstanciaResponse] = []
    sop_vinculado: Optional[dict] = None

    model_config = {"from_attributes": True}
