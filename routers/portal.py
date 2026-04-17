"""E1 — Portal público de tareas para clientes."""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from services import portal_service

router = APIRouter(tags=["Portal"])


# ── Endpoints autenticados (para el estudio) ──────────────────────────────────

@router.post("/api/portal/tokens", status_code=201)
def generar_token(
    cliente_id: int,
    dias_validez: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Genera un token de acceso público para que el cliente vea sus tareas."""
    token = portal_service.generar_token_portal(db, cliente_id, studio_id, dias_validez)
    return {
        "token": token.token,
        "cliente_id": token.cliente_id,
        "expira_at": token.expira_at.isoformat() if token.expira_at else None,
        "activo": token.activo,
    }


@router.delete("/api/portal/tokens/{cliente_id}", status_code=200)
def revocar_token(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Revoca todos los tokens activos del cliente."""
    return portal_service.revocar_token(db, cliente_id, studio_id)


# ── Endpoints públicos (sin autenticación) ────────────────────────────────────

@router.get("/api/portal/cliente/{token}/tareas")
def obtener_tareas_publicas(
    token: str,
    db: Session = Depends(get_db),
):
    """Endpoint público: retorna las tareas del cliente dado su token."""
    return portal_service.obtener_tareas_por_token(db, token)
