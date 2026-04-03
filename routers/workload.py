from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth_dependencies import solo_dueno
from database import get_db
from services import workload_service

router = APIRouter(prefix="/api/workload", tags=["Workload"])


@router.get("/team")
def panel_carga_equipo(
    dias: int = Query(default=14, ge=7, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Panel de carga para todos los empleados activos."""
    return workload_service.obtener_panel_carga(db, dias)


@router.get("/summary")
def resumen_carga(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Resumen ejecutivo para el widget del dashboard."""
    return workload_service.obtener_resumen_carga(db)


@router.get("/employees/{empleado_id}")
def detalle_carga_empleado(
    empleado_id: int,
    dias: int = Query(default=14, ge=7, le=30),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Detalle de carga de un empleado con desglose por cliente."""
    return workload_service.obtener_detalle_empleado(db, empleado_id, dias)
