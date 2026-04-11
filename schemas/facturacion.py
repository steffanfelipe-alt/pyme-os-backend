"""Schemas Pydantic para el módulo de Facturación Electrónica."""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ─── Comprobantes ─────────────────────────────────────────────────────────────

class ComprobanteCreate(BaseModel):
    cliente_id: int
    tipo_comprobante: str           # A, B o C
    concepto: int = 2               # 2 = Servicios
    descripcion_concepto: Optional[str] = None
    importe_neto: float
    alicuota_iva: float = 21.0
    fecha_emision: Optional[date] = None

    @field_validator("tipo_comprobante")
    @classmethod
    def validar_tipo(cls, v: str) -> str:
        if v.upper() not in {"A", "B", "C"}:
            raise ValueError("tipo_comprobante debe ser A, B o C")
        return v.upper()

    @field_validator("alicuota_iva")
    @classmethod
    def validar_alicuota(cls, v: float) -> float:
        if v not in {0.0, 10.5, 21.0, 27.0}:
            raise ValueError("alicuota_iva debe ser 0.0, 10.5, 21.0 o 27.0")
        return v

    @field_validator("importe_neto")
    @classmethod
    def validar_importe(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("importe_neto debe ser mayor a cero")
        return v

    @field_validator("concepto")
    @classmethod
    def validar_concepto(cls, v: int) -> int:
        if v not in {1, 2, 3}:
            raise ValueError("concepto debe ser 1 (Productos), 2 (Servicios) o 3 (Ambos)")
        return v


class ComprobanteResponse(BaseModel):
    id: int
    studio_id: Optional[int]
    cliente_id: int
    tipo_comprobante: str
    punto_venta: int
    numero_comprobante: Optional[int]
    cae: Optional[str]
    fecha_cae_vencimiento: Optional[date]
    fecha_emision: date
    concepto: int
    descripcion_concepto: Optional[str]
    importe_neto: float
    importe_iva: float
    importe_total: float
    alicuota_iva: float
    estado: str
    error_arca: Optional[str]
    enviada_por_email: bool
    enviada_por_telegram: bool
    pdf_url: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RegistrarPagoRequest(BaseModel):
    fecha_pago: Optional[date] = None
    medio_pago: Optional[str] = None   # transferencia / efectivo / cheque / otro
    nota: Optional[str] = None


class PagoResponse(BaseModel):
    id: int
    comprobante_id: int
    fecha_pago: Optional[date]
    medio_pago: Optional[str]
    estado: str
    nota: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Honorarios recurrentes ───────────────────────────────────────────────────

class HonorarioCreate(BaseModel):
    cliente_id: int
    descripcion: str
    importe_neto: float
    alicuota_iva: float = 21.0
    tipo_comprobante: str = "B"
    dia_emision: int = 1

    @field_validator("dia_emision")
    @classmethod
    def validar_dia(cls, v: int) -> int:
        if not (1 <= v <= 28):
            raise ValueError("dia_emision debe estar entre 1 y 28")
        return v


class HonorarioUpdate(BaseModel):
    descripcion: Optional[str] = None
    importe_neto: Optional[float] = None
    alicuota_iva: Optional[float] = None
    tipo_comprobante: Optional[str] = None
    dia_emision: Optional[int] = None
    activo: Optional[bool] = None


class HonorarioResponse(BaseModel):
    id: int
    studio_id: Optional[int]
    cliente_id: int
    descripcion: str
    importe_neto: float
    alicuota_iva: float
    tipo_comprobante: str
    dia_emision: int
    activo: bool
    ultimo_emitido: Optional[date]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Configuración ARCA ───────────────────────────────────────────────────────

class ArcaConfigCreate(BaseModel):
    cuit: str
    punto_venta: int
    certificado_b64: str        # PEM base64-encoded
    clave_privada_b64: str      # PEM base64-encoded
    modo: str = "homologacion"


class ArcaConfigResponse(BaseModel):
    studio_id: int
    cuit: str
    punto_venta: int
    modo: str
    configurado: bool

    class Config:
        from_attributes = True
