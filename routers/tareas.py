from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.tarea import EstadoTarea, PrioridadTarea
from schemas.tarea import TareaCreate, TareaResponse, TareaUpdate
from services import tarea_service

router = APIRouter(prefix="/api/tareas", tags=["Tareas"])


@router.post("", response_model=TareaResponse, status_code=201)
def crear_tarea(
    data: TareaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return tarea_service.crear_tarea(db, data)


@router.get("", response_model=list[TareaResponse], response_model_exclude_none=True)
def listar_tareas(
    cliente_id: Optional[int] = None,
    empleado_id: Optional[int] = None,
    estado: Optional[EstadoTarea] = None,
    prioridad: Optional[PrioridadTarea] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return tarea_service.listar_tareas(db, cliente_id, empleado_id, estado, prioridad, skip, limit)


@router.get("/{tarea_id}", response_model=TareaResponse, response_model_exclude_none=True)
def obtener_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return tarea_service.obtener_tarea(db, tarea_id)


@router.put("/{tarea_id}", response_model=TareaResponse, response_model_exclude_none=True)
def actualizar_tarea(
    tarea_id: int,
    data: TareaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return tarea_service.actualizar_tarea(db, tarea_id, data)


@router.put("/{tarea_id}/asignar", response_model=TareaResponse, response_model_exclude_none=True)
def asignar_empleado(
    tarea_id: int,
    empleado_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return tarea_service.asignar_empleado(db, tarea_id, empleado_id)


@router.delete("/{tarea_id}", status_code=204)
def eliminar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    tarea_service.eliminar_tarea(db, tarea_id)
