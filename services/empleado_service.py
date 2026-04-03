from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.empleado import Empleado
from models.tarea import EstadoTarea, Tarea
from schemas.empleado import (
    CargaDetalleEmpleado,
    CargaResumenEmpleado,
    EmpleadoCreate,
    EmpleadoResponse,
    EmpleadoUpdate,
)
from schemas.cliente import TareaFicha


def crear_empleado(db: Session, data: EmpleadoCreate) -> Empleado:
    existente = db.query(Empleado).filter(Empleado.email == data.email).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un empleado con ese email")

    empleado = Empleado(**data.model_dump())
    db.add(empleado)
    db.commit()
    db.refresh(empleado)
    return empleado


def listar_empleados(
    db: Session,
    skip: int = 0,
    limit: int = 50,
    activo: Optional[bool] = True,
) -> list[Empleado]:
    query = db.query(Empleado)
    if activo is not None:
        query = query.filter(Empleado.activo == activo)
    return query.offset(skip).limit(limit).all()


def obtener_empleado(db: Session, empleado_id: int) -> Empleado:
    empleado = db.query(Empleado).filter(Empleado.id == empleado_id).first()
    if not empleado:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    return empleado


def actualizar_empleado(db: Session, empleado_id: int, data: EmpleadoUpdate) -> Empleado:
    empleado = obtener_empleado(db, empleado_id)
    cambios = data.model_dump(exclude_unset=True)

    if "email" in cambios:
        existente = (
            db.query(Empleado)
            .filter(Empleado.email == cambios["email"], Empleado.id != empleado_id)
            .first()
        )
        if existente:
            raise HTTPException(status_code=409, detail="Ya existe un empleado con ese email")

    for campo, valor in cambios.items():
        setattr(empleado, campo, valor)

    db.commit()
    db.refresh(empleado)
    return empleado


def eliminar_empleado(db: Session, empleado_id: int) -> None:
    empleado = obtener_empleado(db, empleado_id)
    empleado.activo = False
    db.commit()


def _color_carga(pct: float) -> str:
    if pct < 70:
        return "verde"
    if pct <= 90:
        return "amarillo"
    return "rojo"


def listar_carga_empleados(db: Session) -> list[CargaResumenEmpleado]:
    empleados = db.query(Empleado).filter(Empleado.activo == True).all()
    resultado = []
    for emp in empleados:
        pend = db.query(func.count(Tarea.id)).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.pendiente,
            Tarea.activo == True,
        ).scalar() or 0
        en_prog = db.query(func.count(Tarea.id)).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.en_progreso,
            Tarea.activo == True,
        ).scalar() or 0
        horas = round(
            db.query(func.coalesce(func.sum(Tarea.horas_estimadas), 0.0)).filter(
                Tarea.empleado_id == emp.id,
                Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
                Tarea.activo == True,
            ).scalar() or 0.0,
            1,
        )
        pct = round(horas / emp.capacidad_horas_mes * 100, 1) if emp.capacidad_horas_mes else 0.0
        resultado.append(CargaResumenEmpleado(
            empleado_id=emp.id,
            nombre=emp.nombre,
            rol=emp.rol,
            pendientes=pend,
            en_progreso=en_prog,
            horas_estimadas=horas,
            capacidad_horas_mes=emp.capacidad_horas_mes,
            porcentaje_carga=pct,
            color=_color_carga(pct),
        ))
    return resultado


def obtener_carga_empleado(db: Session, empleado_id: int) -> CargaDetalleEmpleado:
    empleado = obtener_empleado(db, empleado_id)
    hoy = date.today()

    tareas_activas = (
        db.query(Tarea)
        .filter(
            Tarea.empleado_id == empleado_id,
            Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
            Tarea.activo == True,
        )
        .order_by(Tarea.fecha_limite.asc().nullslast())
        .all()
    )

    completadas_hoy = db.query(func.count(Tarea.id)).filter(
        Tarea.empleado_id == empleado_id,
        Tarea.estado == EstadoTarea.completada,
        Tarea.fecha_completada == hoy,
        Tarea.activo == True,
    ).scalar() or 0

    tareas_pendientes = [
        TareaFicha(
            id=t.id, titulo=t.titulo, tipo=t.tipo.value, prioridad=t.prioridad.value,
            estado=t.estado.value, fecha_limite=t.fecha_limite,
            horas_estimadas=t.horas_estimadas, empleado_id=t.empleado_id,
        )
        for t in tareas_activas if t.estado == EstadoTarea.pendiente
    ]
    tareas_en_progreso = [
        TareaFicha(
            id=t.id, titulo=t.titulo, tipo=t.tipo.value, prioridad=t.prioridad.value,
            estado=t.estado.value, fecha_limite=t.fecha_limite,
            horas_estimadas=t.horas_estimadas, empleado_id=t.empleado_id,
        )
        for t in tareas_activas if t.estado == EstadoTarea.en_progreso
    ]

    horas_estimadas = round(sum(t.horas_estimadas or 0.0 for t in tareas_activas), 1)

    # Clientes únicos con tareas activas
    cliente_ids = {t.cliente_id for t in tareas_activas}
    from schemas.empleado import ClienteResumenEmpleado
    clientes = db.query(Cliente).filter(Cliente.id.in_(cliente_ids)).all()
    clientes_activos = [
        ClienteResumenEmpleado(id=c.id, nombre=c.nombre, cuit_cuil=c.cuit_cuil)
        for c in clientes
    ]

    return CargaDetalleEmpleado(
        empleado=EmpleadoResponse.model_validate(empleado),
        tareas_pendientes=tareas_pendientes,
        tareas_en_progreso=tareas_en_progreso,
        completadas_hoy=completadas_hoy,
        horas_estimadas_pendientes=horas_estimadas,
        clientes_activos=clientes_activos,
    )
