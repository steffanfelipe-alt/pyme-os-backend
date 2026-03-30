from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from schemas.empleado import (
    CargaDetalleEmpleado,
    CargaResumenEmpleado,
    EmpleadoCreate,
    EmpleadoResponse,
    EmpleadoUpdate,
)
from services import empleado_service

router = APIRouter(prefix="/api/empleados", tags=["Empleados"])


@router.post("", response_model=EmpleadoResponse, status_code=201)
def crear_empleado(
    data: EmpleadoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return empleado_service.crear_empleado(db, data)


@router.get("", response_model=list[EmpleadoResponse], response_model_exclude_none=True)
def listar_empleados(
    skip: int = 0,
    limit: int = 50,
    activo: Optional[bool] = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return empleado_service.listar_empleados(db, skip, limit, activo)


@router.get("/carga", response_model=list[CargaResumenEmpleado])
def listar_carga_empleados(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return empleado_service.listar_carga_empleados(db)


@router.get("/{empleado_id}/tareas", response_model=CargaDetalleEmpleado)
def obtener_carga_empleado(
    empleado_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return empleado_service.obtener_carga_empleado(db, empleado_id)


@router.get("/{empleado_id}", response_model=EmpleadoResponse, response_model_exclude_none=True)
def obtener_empleado(
    empleado_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return empleado_service.obtener_empleado(db, empleado_id)


@router.put("/{empleado_id}", response_model=EmpleadoResponse, response_model_exclude_none=True)
def actualizar_empleado(
    empleado_id: int,
    data: EmpleadoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return empleado_service.actualizar_empleado(db, empleado_id, data)


@router.delete("/{empleado_id}", status_code=204)
def eliminar_empleado(
    empleado_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    empleado_service.eliminar_empleado(db, empleado_id)
