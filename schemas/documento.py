from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from models.documento import EstadoDocumento, TipoDocumento


class DocumentoCreate(BaseModel):
    vencimiento_id: Optional[int] = None


class DocumentoUpdate(BaseModel):
    tipo_documento: Optional[TipoDocumento] = None
    vencimiento_id: Optional[int] = None


class DocumentoResponse(BaseModel):
    id: int
    cliente_id: int
    vencimiento_id: Optional[int]
    nombre_original: str
    ruta_archivo: str
    tipo_documento: TipoDocumento
    confianza: Optional[float]
    resumen: Optional[str]
    metadatos: Optional[dict]
    estado: EstadoDocumento
    activo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
