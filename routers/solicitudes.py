"""E2 — Solicitud automática de documentos faltantes."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from services import solicitud_documento_service

router = APIRouter(prefix="/api/solicitudes-documentos", tags=["Solicitudes"])

_ROL = require_rol("dueno", "contador", "administrativo")


@router.post("/generar", status_code=201)
def generar_solicitudes(
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    """
    Analiza alertas activas y crea solicitudes de documentos para los faltantes
    que aún no hayan sido solicitados.
    """
    creadas = solicitud_documento_service.solicitar_documentos_faltantes(db, studio_id)
    return {"creadas": len(creadas), "solicitudes": creadas}


@router.get("")
def listar_solicitudes(
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    solicitudes = solicitud_documento_service.listar_solicitudes(db, studio_id, cliente_id)
    return [
        {
            "id": s.id,
            "cliente_id": s.cliente_id,
            "vencimiento_id": s.vencimiento_id,
            "tipo_documento": s.tipo_documento,
            "estado": s.estado.value,
            "canal": s.canal,
            "enviada_at": s.enviada_at.isoformat() if s.enviada_at else None,
            "created_at": s.created_at.isoformat(),
        }
        for s in solicitudes
    ]


@router.patch("/{solicitud_id}/enviada")
def marcar_enviada(
    solicitud_id: int,
    canal: str = "email",
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    s = solicitud_documento_service.marcar_enviada(db, solicitud_id, studio_id, canal)
    return {"id": s.id, "estado": s.estado.value, "canal": s.canal}


@router.patch("/{solicitud_id}/recibida")
def marcar_recibida(
    solicitud_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    s = solicitud_documento_service.marcar_recibida(db, solicitud_id, studio_id)
    return {"id": s.id, "estado": s.estado.value}
