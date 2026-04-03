from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import require_rol, solo_dueno, verificar_acceso_cliente
from database import get_db
from models.vencimiento import EstadoVencimiento
from schemas.vencimiento import VencimientoCreate, VencimientoResponse, VencimientoUpdate
from services import vencimiento_service

router = APIRouter(prefix="/api/vencimientos", tags=["Vencimientos"])


@router.post("", response_model=VencimientoResponse, status_code=201)
def crear_vencimiento(
    data: VencimientoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    if current_user.get("rol") == "contador":
        verificar_acceso_cliente(current_user, data.cliente_id, db)
    return vencimiento_service.crear_vencimiento(db, data)


@router.get("", response_model=list[VencimientoResponse], response_model_exclude_none=True)
def listar_vencimientos(
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoVencimiento] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    if current_user.get("rol") == "contador" and cliente_id is not None:
        verificar_acceso_cliente(current_user, cliente_id, db)
    contador_id = current_user.get("empleado_id") if current_user.get("rol") == "contador" else None
    return vencimiento_service.listar_vencimientos(db, cliente_id, estado, skip, limit, contador_id)


@router.get("/{vencimiento_id}", response_model=VencimientoResponse, response_model_exclude_none=True)
def obtener_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    return vencimiento_service.obtener_vencimiento(db, vencimiento_id)


@router.put("/{vencimiento_id}", response_model=VencimientoResponse, response_model_exclude_none=True)
def actualizar_vencimiento(
    vencimiento_id: int,
    data: VencimientoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    return vencimiento_service.actualizar_vencimiento(db, vencimiento_id, data)


@router.delete("/{vencimiento_id}", status_code=204)
def eliminar_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    vencimiento_service.eliminar_vencimiento(db, vencimiento_id)
