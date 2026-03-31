from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from services import alert_service

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@router.get("")
def listar_alertas(
    nivel: str | None = Query(default=None, description="Filtrar por nivel: critica, advertencia, informativa"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Listado de alertas no resueltas, ordenadas por nivel y días restantes."""
    return alert_service.listar_alertas(db, nivel)


@router.get("/summary")
def resumen_alertas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Conteo de alertas activas por nivel."""
    return alert_service.resumen_alertas(db)


@router.post("/generate", status_code=201)
def generar_alertas(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Dispara la generación de alertas para todos los vencimientos pendientes dentro del umbral."""
    return alert_service.generar_alertas(db)


@router.patch("/{alert_id}/mark-seen")
def marcar_vista(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Marca una alerta como vista."""
    return alert_service.marcar_vista(db, alert_id)


@router.patch("/{alert_id}/resolve")
def resolver_alerta(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Marca una alerta como resuelta."""
    return alert_service.resolver_alerta(db, alert_id)
