from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, EmailStr

from models.empleado import RolEmpleado
from schemas.cliente import TareaFicha


class EmpleadoCreate(BaseModel):
    nombre: str
    email: EmailStr
    rol: RolEmpleado
    capacidad_horas_mes: int = 160


class EmpleadoUpdate(BaseModel):
    nombre: Optional[str] = None
    email: Optional[EmailStr] = None
    rol: Optional[RolEmpleado] = None
    capacidad_horas_mes: Optional[int] = None
    activo: Optional[bool] = None


class EmpleadoResponse(BaseModel):
    id: int
    nombre: str
    email: str
    rol: RolEmpleado
    capacidad_horas_mes: int
    activo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClienteResumenEmpleado(BaseModel):
    """Resumen mínimo de cliente para la vista de carga del empleado."""
    id: int
    nombre: str
    cuit_cuil: str

    model_config = {"from_attributes": True}


class CargaResumenEmpleado(BaseModel):
    """Fila de la tabla resumen de carga — un empleado, sus conteos y % de capacidad."""
    empleado_id: int
    nombre: str
    rol: RolEmpleado
    pendientes: int
    en_progreso: int
    horas_estimadas: float
    capacidad_horas_mes: int
    porcentaje_carga: float
    color: str  # "verde" | "amarillo" | "rojo"

    model_config = {"from_attributes": True}


class CargaDetalleEmpleado(BaseModel):
    """Detalle completo de la carga de un empleado específico."""
    empleado: EmpleadoResponse
    tareas_pendientes: list[TareaFicha]
    tareas_en_progreso: list[TareaFicha]
    completadas_hoy: int
    horas_estimadas_pendientes: float
    clientes_activos: list[ClienteResumenEmpleado]

    model_config = {"from_attributes": True}
