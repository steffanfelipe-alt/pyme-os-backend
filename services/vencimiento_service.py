from datetime import date, timedelta
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.vencimiento import EstadoVencimiento, Vencimiento, TipoVencimiento
from schemas.vencimiento import VencimientoCreate, VencimientoUpdate


def _actualizar_estado_si_vencido(db: Session, vencimiento: Vencimiento) -> None:
    if (
        vencimiento.estado == EstadoVencimiento.pendiente
        and vencimiento.fecha_vencimiento < date.today()
    ):
        vencimiento.estado = EstadoVencimiento.vencido
        db.commit()


def crear_vencimiento(db: Session, data: VencimientoCreate) -> Vencimiento:
    cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id, Cliente.activo == True).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    vencimiento = Vencimiento(**data.model_dump())
    db.add(vencimiento)
    db.commit()
    db.refresh(vencimiento)
    return vencimiento


def listar_vencimientos(
    db: Session,
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoVencimiento] = None,
    skip: int = 0,
    limit: int = 200,
    contador_id: Optional[int] = None,
    dias_max: Optional[int] = 180,
) -> list[Vencimiento]:
    query = db.query(Vencimiento)
    if cliente_id is not None:
        query = query.filter(Vencimiento.cliente_id == cliente_id)
    if contador_id is not None:
        query = query.join(Cliente, Vencimiento.cliente_id == Cliente.id).filter(
            Cliente.contador_asignado_id == contador_id
        )
    if estado is not None:
        query = query.filter(Vencimiento.estado == estado)
    # No mostrar vencimientos muy lejanos en el tiempo (default: max 180 días)
    if dias_max is not None and estado not in (EstadoVencimiento.cumplido, EstadoVencimiento.vencido):
        fecha_limite = date.today() + timedelta(days=dias_max)
        query = query.filter(Vencimiento.fecha_vencimiento <= fecha_limite)

    vencimientos = query.order_by(Vencimiento.fecha_vencimiento).offset(skip).limit(limit).all()

    for v in vencimientos:
        _actualizar_estado_si_vencido(db, v)

    return vencimientos


def obtener_vencimiento(db: Session, vencimiento_id: int) -> Vencimiento:
    vencimiento = db.query(Vencimiento).filter(Vencimiento.id == vencimiento_id).first()
    if not vencimiento:
        raise HTTPException(status_code=404, detail="Vencimiento no encontrado")
    _actualizar_estado_si_vencido(db, vencimiento)
    return vencimiento


def actualizar_vencimiento(db: Session, vencimiento_id: int, data: VencimientoUpdate) -> Vencimiento:
    vencimiento = obtener_vencimiento(db, vencimiento_id)
    cambios = data.model_dump(exclude_unset=True)

    if cambios.get("estado") == EstadoVencimiento.cumplido and not cambios.get("fecha_cumplimiento"):
        if not vencimiento.fecha_cumplimiento:
            cambios["fecha_cumplimiento"] = date.today()

    for campo, valor in cambios.items():
        setattr(vencimiento, campo, valor)

    db.commit()
    db.refresh(vencimiento)
    return vencimiento


def eliminar_vencimiento(db: Session, vencimiento_id: int) -> None:
    vencimiento = obtener_vencimiento(db, vencimiento_id)
    db.delete(vencimiento)
    db.commit()
