from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from services import risk_service

router = APIRouter(prefix="/api/risk", tags=["Risk"])


@router.get("/clients")
def listar_clientes_por_riesgo(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Clientes activos ordenados por risk_score descendente."""
    return risk_service.listar_clientes_por_riesgo(db)


@router.post("/clients/{client_id}/calculate")
def calcular_score(
    client_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Recalcula el risk_score de un cliente específico."""
    return risk_service.calcular_score_cliente(db, client_id)


@router.post("/recalculate-all")
def recalcular_todos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Recalcula el score de todos los clientes activos."""
    return risk_service.recalcular_todos(db)
