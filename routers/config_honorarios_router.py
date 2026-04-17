"""Configuración Sección 3 — Honorarios y tarifas."""
from typing import Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from models.config_honorarios import ConfigHonorarios

router = APIRouter(prefix="/config/honorarios", tags=["Config - Honorarios"])


class HonorariosUpdate(BaseModel):
    honorario_monotributista: Optional[float] = None
    honorario_responsable_inscripto: Optional[float] = None
    honorario_sociedad: Optional[float] = None
    honorario_empleador_adicional: Optional[float] = None
    honorario_otro: Optional[float] = None
    ajuste_inflacion_activo: Optional[bool] = None
    ajuste_inflacion_porcentaje: Optional[float] = None


def _get_or_create(db: Session, studio_id: int) -> ConfigHonorarios:
    cfg = db.query(ConfigHonorarios).filter(ConfigHonorarios.studio_id == studio_id).first()
    if not cfg:
        cfg = ConfigHonorarios(studio_id=studio_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("")
def obtener_honorarios(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    cfg = _get_or_create(db, studio_id)
    return {
        "honorario_monotributista": float(cfg.honorario_monotributista or 0),
        "honorario_responsable_inscripto": float(cfg.honorario_responsable_inscripto or 0),
        "honorario_sociedad": float(cfg.honorario_sociedad or 0),
        "honorario_empleador_adicional": float(cfg.honorario_empleador_adicional or 0),
        "honorario_otro": float(cfg.honorario_otro or 0),
        "ajuste_inflacion_activo": cfg.ajuste_inflacion_activo,
        "ajuste_inflacion_porcentaje": float(cfg.ajuste_inflacion_porcentaje or 0),
    }


@router.get("/impacto")
def impacto_honorarios(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
    studio_id: int = Depends(get_studio_id),
):
    """Cuántos clientes se verían afectados al actualizar honorarios base."""
    from models.cliente import Cliente
    total = db.query(Cliente).filter(
        Cliente.studio_id == studio_id,
        Cliente.activo == True,
        Cliente.honorario_personalizado == False,
    ).count()
    return {"clientes_afectados": total}


@router.patch("")
def actualizar_honorarios(
    data: HonorariosUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
    studio_id: int = Depends(get_studio_id),
):
    cfg = _get_or_create(db, studio_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(cfg, field, value)
    db.flush()

    # Propagar a clientes sin honorario personalizado
    _propagar_honorarios(db, studio_id, cfg)
    db.commit()
    return {"ok": True}


def _propagar_honorarios(db: Session, studio_id: int, cfg: ConfigHonorarios) -> None:
    """Actualiza honorario_base de clientes que no tienen honorario personalizado."""
    try:
        from models.cliente import Cliente
        MAP_CATEGORIA = {
            "monotributista": cfg.honorario_monotributista,
            "responsable_inscripto": cfg.honorario_responsable_inscripto,
            "sociedad": cfg.honorario_sociedad,
            "otro": cfg.honorario_otro,
        }
        clientes = db.query(Cliente).filter(
            Cliente.studio_id == studio_id,
            Cliente.activo == True,
            Cliente.honorario_personalizado == False,
        ).all()
        for c in clientes:
            cat = getattr(c, "categoria_fiscal", None) or "otro"
            if hasattr(cat, "value"):
                cat = cat.value
            nuevo = MAP_CATEGORIA.get(str(cat).lower())
            if nuevo is not None and hasattr(c, "honorario_base"):
                c.honorario_base = nuevo
    except Exception:
        pass
