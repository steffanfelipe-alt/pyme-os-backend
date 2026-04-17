from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, solo_dueno
from database import get_db
from services import risk_service

router = APIRouter(prefix="/api/risk", tags=["Risk"])


@router.get("/clients")
def listar_clientes_por_riesgo(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Clientes activos ordenados por risk_score descendente."""
    return risk_service.listar_clientes_por_riesgo(db, studio_id)


@router.post("/clients/{client_id}/calculate")
def calcular_score(
    client_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Recalcula el risk_score. risk_explanation se genera en background (~5s)."""
    resultado = risk_service.calcular_score_cliente(db, client_id, studio_id)
    factores = resultado.pop("_factores", {})
    background_tasks.add_task(
        risk_service.generar_risk_explanation_background,
        client_id,
        factores,
    )
    return resultado


@router.post("/recalculate-all")
def recalcular_todos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Recalcula el score de todos los clientes activos."""
    return risk_service.recalcular_todos(db, studio_id)
