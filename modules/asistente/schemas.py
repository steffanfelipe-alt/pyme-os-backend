from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class AdjuntoBase64(BaseModel):
    nombre_archivo: str
    mime_type: str
    contenido_base64: str


class MensajeEntrante(BaseModel):
    canal: Literal["telegram", "email"]
    tipo_usuario: Literal["empleado", "cliente"]
    identificador_origen: str  # telegram_user_id o email remitente
    contenido: str
    adjuntos: Optional[list[AdjuntoBase64]] = None
    timestamp: Optional[datetime] = None
    mensaje_id_externo: Optional[str] = None


class MensajeProcesado(BaseModel):
    usuario_id: int
    tipo_usuario: str
    intencion: str
    respuesta: str
    requiere_confirmacion: bool
    confirmacion_id: Optional[int] = None
    documentos_procesados: Optional[list[int]] = None


class CanalCreate(BaseModel):
    tipo_usuario: Literal["empleado", "cliente"]
    usuario_id: int
    canal: Literal["telegram", "email"]
    identificador: str


class CanalResponse(BaseModel):
    id: int
    tipo_usuario: str
    usuario_id: int
    canal: str
    identificador: str
    activo: bool


class NotificacionRequest(BaseModel):
    usuario_ids: list[int]
    tipo: str  # "resumen_diario" | "vencimiento_proximo" | "documento_recibido" | "custom"
    canal: Literal["telegram", "email"]
    contenido_custom: Optional[str] = None


class ConfirmarRequest(BaseModel):
    confirmado: bool  # True = SÍ, False = NO/cancelar
