from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, solo_dueno
from database import get_db
from services import profitability_service

router = APIRouter(prefix="/api/profitability", tags=["Profitability"])


@router.get("/clients")
def listar_rentabilidad(
    periodo: str = Query(..., description="Período en formato YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Listado de rentabilidad por cliente para el período, ordenado ascendente."""
    return profitability_service.listar_rentabilidad(db, periodo, studio_id)


@router.get("/clients/{cliente_id}/history")
def historial_cliente(
    cliente_id: int,
    meses: int = Query(default=12, ge=1, le=24),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Últimos N meses de rentabilidad para un cliente."""
    return profitability_service.historial_cliente(db, cliente_id, meses, studio_id)


@router.post("/calculate/{periodo}", status_code=201)
def calcular_periodo(
    periodo: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Calcula y persiste snapshots de rentabilidad para el período dado."""
    return profitability_service.calcular_rentabilidad_periodo(db, periodo, studio_id)
