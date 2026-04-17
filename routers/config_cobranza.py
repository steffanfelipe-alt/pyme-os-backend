"""Configuración Sección 4 — Abonos y cobranza."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from models.studio import Studio

router = APIRouter(prefix="/config/cobranza", tags=["Config - Cobranza"])


class CobranzaUpdate(BaseModel):
    cobro_dia_generacion: Optional[int] = None
    cobro_dias_gracia: Optional[int] = None
    cobro_metodo_default: Optional[str] = None
    cobro_banco: Optional[str] = None
    cobro_cbu_cvu: Optional[str] = None
    cobro_alias: Optional[str] = None
    cobro_titular_cuenta: Optional[str] = None
    cobro_mensaje_automatico: Optional[str] = None


def _get_studio(db: Session, studio_id: int) -> Studio:
    s = db.query(Studio).filter(Studio.id == studio_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Studio no encontrado")
    return s


@router.get("")
def obtener_cobranza(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    return {
        "cobro_dia_generacion": s.cobro_dia_generacion,
        "cobro_dias_gracia": s.cobro_dias_gracia,
        "cobro_metodo_default": s.cobro_metodo_default,
        "cobro_banco": s.cobro_banco,
        "cobro_cbu_cvu": s.cobro_cbu_cvu,
        "cobro_alias": s.cobro_alias,
        "cobro_titular_cuenta": s.cobro_titular_cuenta,
        "cobro_mensaje_automatico": s.cobro_mensaje_automatico,
        "tiene_datos_bancarios": bool(s.cobro_cbu_cvu or s.cobro_alias),
    }


@router.patch("")
def actualizar_cobranza(
    data: CobranzaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    return {"ok": True}
