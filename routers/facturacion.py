"""
Router de Facturación Electrónica (ARCA/AFIP).
Todos los endpoints requieren JWT y filtran por studio_id del token.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth_dependencies import require_rol, solo_dueno
from database import get_db
from schemas.facturacion import (
    ArcaConfigCreate,
    ComprobanteCreate,
    ComprobanteResponse,
    HonorarioCreate,
    HonorarioResponse,
    HonorarioUpdate,
    PagoResponse,
    RegistrarPagoRequest,
)
from services import facturacion_service

router = APIRouter(prefix="/api/facturacion", tags=["Facturación"])


def _studio_id(current_user: dict) -> int:
    sid = current_user.get("studio_id")
    if not sid:
        raise HTTPException(status_code=400, detail="studio_id no encontrado en el token")
    return int(sid)


# ─── Configuración ARCA ───────────────────────────────────────────────────────

@router.get("/config")
def obtener_config(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Retorna la configuración ARCA del estudio (sin certificado ni clave privada)."""
    return facturacion_service.obtener_config_arca(_studio_id(current_user), db)


@router.post("/config")
def guardar_config(
    data: ArcaConfigCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Guarda o actualiza la configuración ARCA del estudio."""
    return facturacion_service.guardar_config_arca(_studio_id(current_user), data, db)


# ─── Comprobantes ─────────────────────────────────────────────────────────────

@router.get("/comprobantes", response_model=list[ComprobanteResponse])
def listar_comprobantes(
    cliente_id: Optional[int] = None,
    estado: Optional[str] = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    return facturacion_service.listar_comprobantes(
        _studio_id(current_user), db, cliente_id, estado, fecha_desde, fecha_hasta
    )


@router.get("/comprobantes/{comp_id}", response_model=ComprobanteResponse)
def obtener_comprobante(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    return facturacion_service._get_comprobante_o_404(comp_id, _studio_id(current_user), db)


@router.post("/comprobantes", response_model=ComprobanteResponse, status_code=201)
def emitir_comprobante(
    data: ComprobanteCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Emite un comprobante electrónico contra ARCA. Flujo completo: auth → número → CAE."""
    return facturacion_service.emitir_comprobante(_studio_id(current_user), data, db)


@router.post("/comprobantes/{comp_id}/enviar")
def enviar_comprobante(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Envía el comprobante al cliente por email y/o Telegram."""
    return facturacion_service.enviar_comprobante(comp_id, _studio_id(current_user), db)


@router.post("/comprobantes/{comp_id}/registrar-pago", response_model=PagoResponse)
def registrar_pago(
    comp_id: int,
    data: RegistrarPagoRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Registra el cobro de un comprobante."""
    return facturacion_service.registrar_pago(comp_id, _studio_id(current_user), data, db)


@router.get("/comprobantes/{comp_id}/pdf")
def obtener_pdf(
    comp_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Retorna la URL del PDF del comprobante. Lo genera si no existe aún."""
    url = facturacion_service.obtener_pdf_url(comp_id, _studio_id(current_user), db)
    return {"pdf_url": url}


# ─── Honorarios recurrentes ───────────────────────────────────────────────────

@router.get("/honorarios", response_model=list[HonorarioResponse])
def listar_honorarios(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    return facturacion_service.listar_honorarios(_studio_id(current_user), db)


@router.post("/honorarios", response_model=HonorarioResponse, status_code=201)
def crear_honorario(
    data: HonorarioCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    return facturacion_service.crear_honorario(_studio_id(current_user), data, db)


@router.put("/honorarios/{hon_id}", response_model=HonorarioResponse)
def actualizar_honorario(
    hon_id: int,
    data: HonorarioUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    return facturacion_service.actualizar_honorario(hon_id, _studio_id(current_user), data, db)


@router.delete("/honorarios/{hon_id}", status_code=204)
def eliminar_honorario(
    hon_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    facturacion_service.eliminar_honorario(hon_id, _studio_id(current_user), db)


@router.post("/honorarios/{hon_id}/emitir-ahora", response_model=ComprobanteResponse)
def emitir_honorario_ahora(
    hon_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Fuerza la emisión inmediata del comprobante definido por esta regla."""
    return facturacion_service.emitir_honorario_ahora(hon_id, _studio_id(current_user), db)


# ─── Pagos ────────────────────────────────────────────────────────────────────

@router.get("/pagos", response_model=list[PagoResponse])
def listar_pagos(
    estado: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    return facturacion_service.listar_pagos(_studio_id(current_user), estado, db)
