"""Configuración Sección 2 — Facturación electrónica AFIP/ARCA."""
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from models.studio import Studio

router = APIRouter(prefix="/config/facturacion", tags=["Config - Facturación"])


class FacturacionUpdate(BaseModel):
    afip_punto_venta: Optional[int] = None
    afip_tipo_comprobante_default: Optional[str] = None
    afip_modo: Optional[str] = None


def _get_studio(db: Session, studio_id: int) -> Studio:
    s = db.query(Studio).filter(Studio.id == studio_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Studio no encontrado")
    return s


@router.get("/estado-afip")
def estado_afip(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    tiene_cert = bool(s.afip_certificado_path)
    tiene_clave = bool(s.afip_clave_privada_path)
    estado = "sin_configurar"
    if tiene_cert and tiene_clave and s.afip_punto_venta:
        estado = "configurado"
    return {
        "estado": estado,
        "tiene_certificado": tiene_cert,
        "tiene_clave_privada": tiene_clave,
        "punto_venta": s.afip_punto_venta,
        "tipo_comprobante_default": s.afip_tipo_comprobante_default,
        "modo": s.afip_modo,
        "cuit": s.cuit,
        "condicion_iva": s.condicion_iva,
    }


@router.post("/credenciales")
async def subir_credenciales(
    certificado: UploadFile = File(...),
    clave_privada: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
    studio_id: int = Depends(get_studio_id),
):
    import os, shutil
    os.makedirs("uploads/afip", exist_ok=True)
    cert_path = f"uploads/afip/studio_{studio_id}_cert.pem"
    key_path = f"uploads/afip/studio_{studio_id}_key.key"
    with open(cert_path, "wb") as f:
        shutil.copyfileobj(certificado.file, f)
    with open(key_path, "wb") as f:
        shutil.copyfileobj(clave_privada.file, f)
    s = _get_studio(db, studio_id)
    s.afip_certificado_path = cert_path
    s.afip_clave_privada_path = key_path
    db.commit()
    return {"ok": True, "certificado_path": cert_path}


@router.patch("/config")
def actualizar_config_afip(
    data: FacturacionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    return {"ok": True}


@router.post("/test-conexion")
def test_conexion_afip(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    if not s.afip_certificado_path or not s.afip_clave_privada_path:
        return {"ok": False, "mensaje": "Faltan credenciales AFIP"}
    try:
        from services.arca_service import test_conexion
        resultado = test_conexion(s.afip_certificado_path, s.afip_clave_privada_path, s.afip_modo)
        return {"ok": True, "mensaje": resultado}
    except Exception as e:
        return {"ok": False, "mensaje": str(e)}
