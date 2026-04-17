"""
Módulo de Alertas — spec: Backend + Frontend completo.
URLs: /alertas (nuevo módulo separado del legacy /api/alerts)
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from services import alert_service

router = APIRouter(prefix="/alertas", tags=["Alertas"])


# ─── Schemas ─────────────────────────────────────────────────────────────────

class AlertaManualRequest(BaseModel):
    cliente_id: int
    titulo: str
    mensaje: str
    canal: str = "email"  # 'email' | 'portal' | 'ambos'
    tipo_vencimiento: Optional[str] = None
    tipo_documento: Optional[str] = None
    documento_referencia: Optional[str] = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
def listar_alertas(
    tipo: Optional[str] = Query(default=None),
    cliente_id: Optional[int] = Query(default=None),
    incluir_resueltas: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Lista alertas con filtros opcionales por tipo y cliente_id."""
    return alert_service.listar_alertas_v2(db, studio_id, tipo, cliente_id, incluir_resueltas)


@router.get("/resumen")
def resumen_por_tipo(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Conteo de alertas activas agrupado por tipo."""
    return alert_service.resumen_por_tipo(db, studio_id)


@router.post("/manual", status_code=201)
def crear_alerta_manual(
    data: AlertaManualRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Crea una alerta manual del contador hacia un cliente con canal de envío."""
    return alert_service.crear_alerta_manual(db, studio_id, data.model_dump())


@router.post("/generar-triggers", status_code=200)
def generar_triggers(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
    studio_id: int = Depends(get_studio_id),
):
    """Dispara todos los triggers automáticos: mora, riesgo, tareas vencidas, documentación, vencimientos."""
    return alert_service.generar_todos_los_triggers(db, studio_id)


@router.patch("/{alerta_id}/resolver")
def resolver_alerta(
    alerta_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Marca la alerta como resuelta."""
    return alert_service.resolver_alerta(db, alerta_id, studio_id)


@router.patch("/{alerta_id}/ignorar")
def ignorar_alerta(
    alerta_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Descarta la alerta sin marcarla como resuelta."""
    return alert_service.ignorar_alerta(db, alerta_id, studio_id)
