from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel

from models.vencimiento import TipoVencimiento


class VencimientoSinDoc(BaseModel):
    cliente_id: int
    cliente_nombre: str
    tipo: TipoVencimiento
    fecha_vencimiento: date
    dias_restantes: int
    urgencia: str  # "CRITICO" | "URGENTE" | "PROXIMO"
    contador_nombre: Optional[str]


class ClienteSinActividad(BaseModel):
    cliente_id: int
    nombre: str
    ultima_actividad: Optional[datetime]
    dias_inactivo: int
    contador_nombre: Optional[str]


class TareaRetrasada(BaseModel):
    tarea_id: int
    titulo: str
    cliente_nombre: str
    contador_nombre: Optional[str]
    dias_retraso: int


class ResumenAlertas(BaseModel):
    criticas: int
    advertencias: int
    informativas: int


class BloqueRiesgo(BaseModel):
    vencimientos_sin_docs: list[VencimientoSinDoc]
    clientes_sin_actividad: list[ClienteSinActividad]
    tareas_retrasadas: list[TareaRetrasada]
    alertas_activas: ResumenAlertas


class CargaContador(BaseModel):
    empleado_id: int
    nombre: str
    rol: str
    horas_comprometidas: float
    horas_disponibles: float
    porcentaje_carga: float
    nivel: str  # "disponible" | "ocupado" | "sobrecargado"
    cantidad_tareas: int
    color: str  # "verde" | "amarillo" | "rojo"


class CompletadasATiempo(BaseModel):
    total_pct: float
    mes_anterior_pct: Optional[float]


class TiempoPromedioTipo(BaseModel):
    tipo: str
    promedio_horas: float
    cantidad: int


class IndiceConcentracion(BaseModel):
    alerta: bool
    top_contador_pct: float
    mensaje: Optional[str]


class BloqueCarga(BaseModel):
    carga_por_contador: list[CargaContador]
    completadas_a_tiempo: CompletadasATiempo
    tiempo_promedio_resolucion: list[TiempoPromedioTipo]
    indice_concentracion: IndiceConcentracion


class TiempoRealCliente(BaseModel):
    cliente_id: int
    nombre: str
    horas_mes: float


class DocumentacionCliente(BaseModel):
    cliente_id: int
    nombre: str
    vencimientos_total: int
    con_documentacion: int
    pct: float


class EvolucionMensual(BaseModel):
    mes: str  # "2026-03"
    activos: int
    altas: int
    bajas: int


class RentabilidadCliente(BaseModel):
    cliente_id: int
    nombre: str
    honorarios: Optional[float]
    horas_mes: float
    costo_hora_estimado: Optional[float]
    semaforo: str  # "rentable" | "neutro" | "deficitario" | "sin_datos"


class BloqueSalud(BaseModel):
    tiempo_real_por_cliente: list[TiempoRealCliente]
    documentacion_por_cliente: list[DocumentacionCliente]
    evolucion_clientes: list[EvolucionMensual]
    rentabilidad_por_cliente: list[RentabilidadCliente]


class DashboardResponse(BaseModel):
    bloque_riesgo: BloqueRiesgo
    bloque_carga: BloqueCarga
    bloque_salud: BloqueSalud
    generado_en: datetime
    filtrado_por_contador: Optional[int]
