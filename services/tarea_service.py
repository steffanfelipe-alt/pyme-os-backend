from datetime import date, datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.empleado import Empleado
from models.tarea import EstadoTarea, PrioridadTarea, Tarea
from models.tarea_sesion import TareaSesion
from schemas.tarea import TareaCreate, TareaUpdate
from services import profitability_service, risk_service


def crear_tarea(db: Session, data: TareaCreate) -> Tarea:
    if data.cliente_id is not None:
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

    completando = cambios.get("estado") == EstadoTarea.completada and tarea.estado != EstadoTarea.completada

    for campo, valor in cambios.items():
        setattr(tarea, campo, valor)

    db.commit()
    db.refresh(tarea)

    if completando:
        periodo = (tarea.fecha_completada or date.today()).strftime("%Y-%m")
        try:
            profitability_service.calcular_rentabilidad_periodo(db, periodo)
        except Exception:
            pass
        try:
            risk_service.calcular_score_cliente(db, tarea.cliente_id)
        except Exception:
            pass

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


# ─── Tracking de tiempo ───────────────────────────────────────────────────────

def iniciar_tarea(db: Session, tarea_id: int, empleado_id: Optional[int]) -> Tarea:
    tarea = obtener_tarea(db, tarea_id)

    if tarea.estado == EstadoTarea.completada:
        raise HTTPException(status_code=400, detail="No se puede iniciar una tarea ya completada")

    sesion_activa = db.query(TareaSesion).filter(
        TareaSesion.tarea_id == tarea_id, TareaSesion.fin == None
    ).first()
    if sesion_activa:
        raise HTTPException(status_code=400, detail="La tarea ya tiene una sesión activa")

    sesion = TareaSesion(
        tarea_id=tarea_id,
        empleado_id=empleado_id,
        inicio=datetime.now(timezone.utc),
    )
    db.add(sesion)

    tarea.estado = EstadoTarea.en_progreso
    db.commit()
    db.refresh(tarea)
    return tarea


def pausar_tarea(db: Session, tarea_id: int) -> Tarea:
    tarea = obtener_tarea(db, tarea_id)

    if tarea.estado != EstadoTarea.en_progreso:
        raise HTTPException(status_code=400, detail="Solo se puede pausar una tarea en curso")

    _cerrar_sesion_activa(db, tarea_id)

    tarea.estado = EstadoTarea.pendiente
    db.commit()
    db.refresh(tarea)
    return tarea


def completar_tarea(db: Session, tarea_id: int) -> Tarea:
    tarea = obtener_tarea(db, tarea_id)

    if tarea.estado == EstadoTarea.completada:
        raise HTTPException(status_code=400, detail="La tarea ya está completada")

    _cerrar_sesion_activa(db, tarea_id)

    tarea.estado = EstadoTarea.completada
    tarea.fecha_completada = date.today()
    db.commit()
    db.refresh(tarea)

    periodo = tarea.fecha_completada.strftime("%Y-%m")
    try:
        profitability_service.calcular_rentabilidad_periodo(db, periodo)
    except Exception:
        pass
    try:
        risk_service.calcular_score_cliente(db, tarea.cliente_id)
    except Exception:
        pass

    return tarea


def obtener_tiempo_tarea(db: Session, tarea_id: int) -> dict:
    tarea = obtener_tarea(db, tarea_id)
    sesiones = (
        db.query(TareaSesion)
        .filter(TareaSesion.tarea_id == tarea_id)
        .order_by(TareaSesion.inicio)
        .all()
    )
    sesion_activa = next((s for s in sesiones if s.fin is None), None)
    return {
        "tarea_id": tarea_id,
        "horas_estimadas": tarea.horas_estimadas,
        "horas_reales": tarea.horas_reales,
        "sesion_activa": sesion_activa is not None,
        "sesiones": [
            {
                "id": s.id,
                "empleado_id": s.empleado_id,
                "inicio": s.inicio.isoformat(),
                "fin": s.fin.isoformat() if s.fin else None,
                "minutos": s.minutos,
            }
            for s in sesiones
        ],
    }


def _cerrar_sesion_activa(db: Session, tarea_id: int) -> None:
    """Cierra la sesión abierta y suma los minutos al total de la tarea."""
    sesion = db.query(TareaSesion).filter(
        TareaSesion.tarea_id == tarea_id, TareaSesion.fin == None
    ).first()
    if not sesion:
        return

    ahora = datetime.now(timezone.utc)
    sesion.fin = ahora
    inicio = sesion.inicio if sesion.inicio.tzinfo else sesion.inicio.replace(tzinfo=timezone.utc)
    sesion.minutos = max(1, int((ahora - inicio).total_seconds() // 60))

    tarea = db.query(Tarea).filter(Tarea.id == tarea_id).first()
    if tarea:
        tarea.horas_reales = (tarea.horas_reales or 0) + sesion.minutos / 60
    # El commit lo hace el endpoint que llama a esta función
