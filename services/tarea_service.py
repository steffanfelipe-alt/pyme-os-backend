from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.empleado import Empleado
from models.tarea import EstadoTarea, PrioridadTarea, Tarea
from schemas.tarea import TareaCreate, TareaUpdate


def crear_tarea(db: Session, data: TareaCreate) -> Tarea:
    cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id, Cliente.activo == True).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if data.empleado_id is not None:
        empleado = db.query(Empleado).filter(
            Empleado.id == data.empleado_id, Empleado.activo == True
        ).first()
        if not empleado:
            raise HTTPException(status_code=404, detail="Empleado no encontrado o inactivo")

    tarea = Tarea(**data.model_dump())
    db.add(tarea)
    db.commit()
    db.refresh(tarea)
    return tarea


def listar_tareas(
    db: Session,
    cliente_id: Optional[int] = None,
    empleado_id: Optional[int] = None,
    estado: Optional[EstadoTarea] = None,
    prioridad: Optional[PrioridadTarea] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Tarea]:
    query = db.query(Tarea).filter(Tarea.activo == True)
    if cliente_id is not None:
        query = query.filter(Tarea.cliente_id == cliente_id)
    if empleado_id is not None:
        query = query.filter(Tarea.empleado_id == empleado_id)
    if estado is not None:
        query = query.filter(Tarea.estado == estado)
    if prioridad is not None:
        query = query.filter(Tarea.prioridad == prioridad)
    return query.offset(skip).limit(limit).all()


def obtener_tarea(db: Session, tarea_id: int) -> Tarea:
    tarea = db.query(Tarea).filter(Tarea.id == tarea_id, Tarea.activo == True).first()
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return tarea


def actualizar_tarea(db: Session, tarea_id: int, data: TareaUpdate) -> Tarea:
    tarea = obtener_tarea(db, tarea_id)
    cambios = data.model_dump(exclude_unset=True)

    if cambios.get("estado") == EstadoTarea.completada and not cambios.get("fecha_completada"):
        if not tarea.fecha_completada:
            cambios["fecha_completada"] = date.today()

    if "empleado_id" in cambios and cambios["empleado_id"] is not None:
        empleado = db.query(Empleado).filter(
            Empleado.id == cambios["empleado_id"], Empleado.activo == True
        ).first()
        if not empleado:
            raise HTTPException(status_code=404, detail="Empleado no encontrado o inactivo")

    for campo, valor in cambios.items():
        setattr(tarea, campo, valor)

    db.commit()
    db.refresh(tarea)
    return tarea


def asignar_empleado(db: Session, tarea_id: int, empleado_id: Optional[int]) -> Tarea:
    tarea = obtener_tarea(db, tarea_id)
    if empleado_id is not None:
        empleado = db.query(Empleado).filter(
            Empleado.id == empleado_id, Empleado.activo == True
        ).first()
        if not empleado:
            raise HTTPException(status_code=404, detail="Empleado no encontrado o inactivo")
    tarea.empleado_id = empleado_id
    db.commit()
    db.refresh(tarea)
    return tarea


def eliminar_tarea(db: Session, tarea_id: int) -> None:
    tarea = obtener_tarea(db, tarea_id)
    tarea.activo = False
    db.commit()
