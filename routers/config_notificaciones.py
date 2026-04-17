"""Configuración Sección 6 — Notificaciones y alertas."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from models.studio import Studio

router = APIRouter(prefix="/config/notificaciones", tags=["Config - Notificaciones"])


class NotificacionesUpdate(BaseModel):
    alerta_vencimiento_dias: Optional[int] = None
    alerta_documentacion_dias: Optional[int] = None
    alerta_cobro_gracia_dias: Optional[int] = None
    alerta_riesgo_umbral: Optional[int] = None
    notif_resumen_diario_telegram: Optional[bool] = None
    notif_resumen_semanal_email: Optional[bool] = None
    notif_criticas_email: Optional[bool] = None
    notif_criticas_telegram: Optional[bool] = None
    email_nombre_remitente: Optional[str] = None
    email_firma: Optional[str] = None


def _get_studio(db: Session, studio_id: int) -> Studio:
    s = db.query(Studio).filter(Studio.id == studio_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Studio no encontrado")
    return s


@router.get("")
def obtener_notificaciones(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    return {
        "alerta_vencimiento_dias": s.alerta_vencimiento_dias,
        "alerta_documentacion_dias": s.alerta_documentacion_dias,
        "alerta_cobro_gracia_dias": s.alerta_cobro_gracia_dias,
        "alerta_riesgo_umbral": s.alerta_riesgo_umbral,
        "notif_resumen_diario_telegram": s.notif_resumen_diario_telegram,
        "notif_resumen_semanal_email": s.notif_resumen_semanal_email,
        "notif_criticas_email": s.notif_criticas_email,
        "notif_criticas_telegram": s.notif_criticas_telegram,
        "email_nombre_remitente": s.email_nombre_remitente,
        "email_firma": s.email_firma,
    }


@router.patch("")
def actualizar_notificaciones(
    data: NotificacionesUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    return {"ok": True}
