from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.vencimiento import EstadoVencimiento
from schemas.vencimiento import VencimientoCreate, VencimientoResponse, VencimientoUpdate
from services import vencimiento_service

router = APIRouter(prefix="/api/vencimientos", tags=["Vencimientos"])


@router.post("", response_model=VencimientoResponse, status_code=201)
def crear_vencimiento(
    data: VencimientoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return vencimiento_service.crear_vencimiento(db, data)


@router.get("", response_model=list[VencimientoResponse], response_model_exclude_none=True)
def listar_vencimientos(
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoVencimiento] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return vencimiento_service.listar_vencimientos(db, cliente_id, estado, skip, limit)


@router.get("/{vencimiento_id}", response_model=VencimientoResponse, response_model_exclude_none=True)
def obtener_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return vencimiento_service.obtener_vencimiento(db, vencimiento_id)


@router.put("/{vencimiento_id}", response_model=VencimientoResponse, response_model_exclude_none=True)
def actualizar_vencimiento(
    vencimiento_id: int,
    data: VencimientoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return vencimiento_service.actualizar_vencimiento(db, vencimiento_id, data)


@router.delete("/{vencimiento_id}", status_code=204)
def eliminar_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    vencimiento_service.eliminar_vencimiento(db, vencimiento_id)
