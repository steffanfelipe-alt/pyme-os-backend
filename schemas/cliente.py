import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, computed_field, field_validator

from models.cliente import CondicionFiscal, TipoPersona


class EstadoAlerta(str, enum.Enum):
    verde = "verde"
    amarillo = "amarillo"
    rojo = "rojo"
    sin_datos = "sin_datos"


class ClienteCreate(BaseModel):
    tipo_persona: TipoPersona
    nombre: str
    cuit_cuil: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    email_notificaciones: Optional[str] = None
    acepta_notificaciones: bool = True
    condicion_fiscal: CondicionFiscal
    contador_asignado_id: Optional[int] = None
    notas: Optional[str] = None
    plantilla_aplicada: bool = False
    honorarios_mensuales: Optional[Decimal] = None
    satisfaccion: Optional[int] = None

    @field_validator("cuit_cuil")
    @classmethod
    def validar_cuit(cls, v: str) -> str:
        clean = v.replace("-", "").replace(" ", "")
        if not clean.isdigit() or len(clean) != 11:
            raise ValueError("CUIT/CUIL debe tener 11 dígitos numéricos")

        coeficientes = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
        suma = sum(int(clean[i]) * coeficientes[i] for i in range(10))
        resto = suma % 11
        if resto == 1:
            raise ValueError("CUIT/CUIL inválido")
        digito_esperado = 0 if resto == 0 else 11 - resto
        if int(clean[10]) != digito_esperado:
            raise ValueError("CUIT/CUIL inválido: dígito verificador incorrecto")

        return v


class ClienteUpdate(BaseModel):
    tipo_persona: Optional[TipoPersona] = None
    nombre: Optional[str] = None
    cuit_cuil: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    email_notificaciones: Optional[str] = None
    acepta_notificaciones: Optional[bool] = None
    condicion_fiscal: Optional[CondicionFiscal] = None
    contador_asignado_id: Optional[int] = None
    notas: Optional[str] = None
    plantilla_aplicada: Optional[bool] = None
    honorarios_mensuales: Optional[Decimal] = None
    satisfaccion: Optional[int] = None
    activo: Optional[bool] = None


class ClienteResponse(BaseModel):
    id: int
    tipo_persona: TipoPersona
    nombre: str
    cuit_cuil: str
    email: Optional[str]
    telefono: Optional[str]
    telefono_whatsapp: Optional[str]
    email_notificaciones: Optional[str]
    acepta_notificaciones: bool
    condicion_fiscal: CondicionFiscal
    contador_asignado_id: Optional[int]
    notas: Optional[str]
    plantilla_aplicada: bool
    honorarios_mensuales: Optional[Decimal]
    satisfaccion: Optional[int]
    activo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClienteResumen(BaseModel):
    """Schema para la lista principal del CRM — incluye campos calculados."""
    id: int
    tipo_persona: TipoPersona
    nombre: str
    cuit_cuil: str
    condicion_fiscal: CondicionFiscal
    contador_asignado_id: Optional[int]
    activo: bool
    # Campos calculados en runtime (nunca persistidos)
    proximo_vencimiento: Optional[date]
    tareas_pendientes: int
    ultima_actividad: Optional[datetime]
    estado_alerta: EstadoAlerta

    @computed_field
    @property
    def dias_para_vencer(self) -> Optional[int]:
        if self.proximo_vencimiento is None:
            return None
        return (self.proximo_vencimiento - date.today()).days

    model_config = {"from_attributes": True}


# --- Schemas para la ficha completa ---

class ContadorInfo(BaseModel):
    id: int
    nombre: str
    email: str
    rol: str

    model_config = {"from_attributes": True}


class VencimientoFicha(BaseModel):
    id: int
    tipo: str
    descripcion: str
    fecha_vencimiento: date
    fecha_cumplimiento: Optional[date]
    estado: str
    dias_para_vencer: int

    model_config = {"from_attributes": True}


class TareaFicha(BaseModel):
    id: int
    titulo: str
    tipo: str
    prioridad: str
    estado: str
    fecha_limite: Optional[date]
    tiempo_estimado: Optional[int]
    empleado_id: Optional[int]

    model_config = {"from_attributes": True}


class FichaClienteResponse(BaseModel):
    cliente: ClienteResponse
    contador_principal: Optional[ContadorInfo]
    participantes_tareas: list[ContadorInfo]
    vencimientos: dict
    tareas: dict
    estado_alerta: EstadoAlerta
    documentos: None = None
