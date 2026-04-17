"""Configuración Sección 1 — Perfil del estudio."""
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from models.studio import Studio

router = APIRouter(prefix="/config/perfil", tags=["Config - Perfil"])


class PerfilUpdate(BaseModel):
    nombre: Optional[str] = None
    cuit: Optional[str] = None
    razon_social: Optional[str] = None
    condicion_iva: Optional[str] = None
    direccion_fiscal: Optional[str] = None
    telefono_contacto: Optional[str] = None
    email_contacto: Optional[str] = None
    nombre_responsable: Optional[str] = None
    provincia_principal: Optional[str] = None
    tarifa_horaria_interna: Optional[float] = None


def _get_studio(db: Session, studio_id: int) -> Studio:
    s = db.query(Studio).filter(Studio.id == studio_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Studio no encontrado")
    return s


@router.get("")
def obtener_perfil(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    return {
        "nombre": s.nombre,
        "cuit": s.cuit,
        "razon_social": s.razon_social,
        "condicion_iva": s.condicion_iva,
        "direccion_fiscal": s.direccion_fiscal,
        "telefono_contacto": s.telefono_contacto,
        "email_contacto": s.email_contacto,
        "nombre_responsable": s.nombre_responsable,
        "logo_url": s.logo_url,
        "provincia_principal": s.provincia_principal,
        "tarifa_horaria_interna": float(s.tarifa_horaria_interna or 0),
    }


@router.patch("")
def actualizar_perfil(
    data: PerfilUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return {"ok": True}


@router.post("/logo")
async def subir_logo(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    import os, shutil
    os.makedirs("uploads/logos", exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "png"
    path = f"uploads/logos/studio_{studio_id}.{ext}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    url = f"/uploads/logos/studio_{studio_id}.{ext}"
    s = _get_studio(db, studio_id)
    s.logo_url = url
    db.commit()
    return {"logo_url": url}
