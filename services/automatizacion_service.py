"""
CRUD de Automatizacion — sin llamadas a Claude API.
La lógica de IA vive en optimizador_service.py.
"""
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.proceso import Automatizacion, ProcesoTemplate
from schemas.automatizacion import AutomatizacionUpdate

logger = logging.getLogger("pymeos")


def crear_automatizacion(
    db: Session,
    template_id: int,
    flujo_json: dict,
    analisis_pasos: dict,
    ahorro_horas_mes: float,
) -> Automatizacion:
    template = db.query(ProcesoTemplate).filter(
        ProcesoTemplate.id == template_id, ProcesoTemplate.activo == True
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")

    existente = db.query(Automatizacion).filter(Automatizacion.template_id == template_id).first()
    if existente:
        # Actualizar en lugar de duplicar
        existente.flujo_json = flujo_json
        existente.analisis_pasos = analisis_pasos
        existente.ahorro_horas_mes = ahorro_horas_mes
        db.commit()
        db.refresh(existente)
        return existente

    automatizacion = Automatizacion(
        template_id=template_id,
        flujo_json=flujo_json,
        analisis_pasos=analisis_pasos,
        ahorro_horas_mes=ahorro_horas_mes,
    )
    db.add(automatizacion)
    db.commit()
    db.refresh(automatizacion)
    return automatizacion


def listar_automatizaciones(db: Session) -> list[Automatizacion]:
    return db.query(Automatizacion).order_by(Automatizacion.created_at.desc()).all()


def obtener_automatizacion(db: Session, automatizacion_id: int) -> Automatizacion:
    aut = db.query(Automatizacion).filter(Automatizacion.id == automatizacion_id).first()
    if not aut:
        raise HTTPException(status_code=404, detail="Automatización no encontrada")
    return aut


def obtener_automatizacion_por_template(db: Session, template_id: int) -> Automatizacion:
    aut = db.query(Automatizacion).filter(Automatizacion.template_id == template_id).first()
    if not aut:
        raise HTTPException(status_code=404, detail="No hay automatización para este template")
    return aut


def actualizar_automatizacion(
    db: Session,
    automatizacion_id: int,
    data: AutomatizacionUpdate,
) -> Automatizacion:
    aut = obtener_automatizacion(db, automatizacion_id)
    for campo, valor in data.model_dump(exclude_none=True).items():
        setattr(aut, campo, valor)
    db.commit()
    db.refresh(aut)
    return aut


def eliminar_automatizacion(db: Session, automatizacion_id: int) -> None:
    aut = obtener_automatizacion(db, automatizacion_id)
    db.delete(aut)
    db.commit()
