"""Configuración Sección 7 — Calendario fiscal."""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from models.config_calendario import ConfigCalendario

router = APIRouter(prefix="/config/calendario-fiscal", tags=["Config - Calendario"])

# Fechas de IIBB por provincia
PROVINCIAS_IIBB = {
    "CABA": 22, "Buenos Aires": 13, "Córdoba": 15,
    "Santa Fe": 15, "Mendoza": 20, "Tucumán": 15,
    "Entre Ríos": 15, "Salta": 15, "Misiones": 15,
    "Chaco": 15, "San Juan": 15, "Corrientes": 15,
    "Santiago del Estero": 15, "San Luis": 15, "Jujuy": 15,
    "Río Negro": 15, "Neuquén": 15, "Formosa": 15,
    "Chubut": 15, "La Rioja": 15, "Santa Cruz": 15,
    "Catamarca": 15, "La Pampa": 15, "Tierra del Fuego": 15,
}


class CalendarioUpdate(BaseModel):
    iibb_provincia: Optional[str] = None
    iibb_dia_vencimiento: Optional[int] = None
    bienes_personales_mes: Optional[int] = None
    bienes_personales_dia: Optional[int] = None
    observaciones: Optional[str] = None


def _get_or_create(db: Session, studio_id: int) -> ConfigCalendario:
    cfg = db.query(ConfigCalendario).filter(ConfigCalendario.studio_id == studio_id).first()
    if not cfg:
        cfg = ConfigCalendario(studio_id=studio_id)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@router.get("")
def obtener_calendario(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    cfg = _get_or_create(db, studio_id)
    return {
        "iibb_provincia": cfg.iibb_provincia,
        "iibb_dia_vencimiento": cfg.iibb_dia_vencimiento,
        "bienes_personales_mes": cfg.bienes_personales_mes,
        "bienes_personales_dia": cfg.bienes_personales_dia,
        "observaciones": cfg.observaciones,
    }


@router.patch("")
def actualizar_calendario(
    data: CalendarioUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
    studio_id: int = Depends(get_studio_id),
):
    cfg = _get_or_create(db, studio_id)
    updates = data.model_dump(exclude_none=True)
    # Si cambia la provincia, actualizar el día automáticamente
    if "iibb_provincia" in updates and "iibb_dia_vencimiento" not in updates:
        updates["iibb_dia_vencimiento"] = PROVINCIAS_IIBB.get(updates["iibb_provincia"], 15)
    for field, value in updates.items():
        setattr(cfg, field, value)
    db.commit()
    return {"ok": True}


@router.get("/provincias")
def listar_provincias(
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    return [
        {"provincia": prov, "dia_vencimiento": dia}
        for prov, dia in PROVINCIAS_IIBB.items()
    ]
