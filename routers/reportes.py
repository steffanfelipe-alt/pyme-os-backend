from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import solo_dueno
from database import get_db
from models.vencimiento import EstadoVencimiento
from services import reportes_service

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])


# ─── Studio Config ────────────────────────────────────────────────────────────

@router.get("/config")
def obtener_config(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Retorna la configuración del estudio (tarifa-hora, moneda, zona horaria)."""
    return reportes_service.obtener_config(db)


class ConfigUpdate(BaseModel):
    tarifa_hora_pesos: Optional[float] = None
    moneda: Optional[str] = None
    zona_horaria: Optional[str] = None


@router.put("/config")
def actualizar_config(
    data: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Actualiza tarifa-hora, moneda y/o zona horaria del estudio."""
    return reportes_service.actualizar_config(
        db, data.tarifa_hora_pesos, data.moneda, data.zona_horaria
    )


# ─── Reporte 1: Carga por empleado ───────────────────────────────────────────

@router.get("/carga")
def reporte_carga(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Carga de trabajo por empleado para el período YYYY-MM.
    Si no se envía período, usa el mes actual.
    """
    return reportes_service.reporte_carga(db, periodo)


# ─── Reporte 2: Rentabilidad por cliente ─────────────────────────────────────

@router.get("/rentabilidad")
def reporte_rentabilidad(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Rentabilidad por cliente usando horas reales de procesos + tarifa-hora configurada.
    Requiere tarifa-hora configurada en /reportes/config.
    """
    return reportes_service.reporte_rentabilidad(db, periodo)


# ─── Reporte 3: Vencimientos del período ─────────────────────────────────────

@router.get("/vencimientos")
def reporte_vencimientos(
    periodo: Optional[str] = None,
    estado: Optional[EstadoVencimiento] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Vencimientos del período con alertas para los que vencen en <= 7 días.
    Filtro opcional por estado.
    """
    return reportes_service.reporte_vencimientos(db, periodo, estado)


# ─── Reporte 4: Eficiencia de procesos ───────────────────────────────────────

@router.get("/procesos")
def reporte_procesos(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Eficiencia de procesos: desviación entre tiempo estimado y real.
    Solo incluye procesos con 5+ instancias completadas en el período.
    """
    return reportes_service.reporte_procesos(db, periodo)


# ─── Resumen ejecutivo ────────────────────────────────────────────────────────

@router.get("/resumen")
def reporte_resumen(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Resumen ejecutivo consolidado de los 4 reportes.
    Consume datos ya calculados — no recalcula todo de cero.
    """
    return reportes_service.reporte_resumen(db, periodo)
