"""
Servicio de templates e instancias de procesos.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.proceso import (
    EstadoInstancia,
    EstadoPasoInstancia,
    ProcesoPasoInstancia,
    ProcesoPasoTemplate,
    ProcesoInstancia,
    ProcesoTemplate,
)
from models.vencimiento import Vencimiento
from schemas.proceso import (
    ProcesoInstanciaCreate,
    ProcesoInstanciaUpdate,
    ProcesoPasoInstanciaUpdate,
    ProcesoPasoTemplateCreate,
    ProcesoPasoTemplateUpdate,
    ProcesoTemplateCreate,
    ProcesoTemplateUpdate,
)

logger = logging.getLogger("pymeos")


# ─── Templates ────────────────────────────────────────────────────────────────

def crear_template(db: Session, data: ProcesoTemplateCreate, empleado_id: Optional[int]) -> ProcesoTemplate:
    template = ProcesoTemplate(**data.model_dump(), creado_por=empleado_id)
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def listar_templates(db: Session) -> list[ProcesoTemplate]:
    return (
        db.query(ProcesoTemplate)
        .filter(ProcesoTemplate.activo == True)
        .order_by(ProcesoTemplate.nombre)
        .all()
    )


def obtener_template(db: Session, template_id: int) -> ProcesoTemplate:
    template = db.query(ProcesoTemplate).filter(ProcesoTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    return template


def actualizar_template(
    db: Session,
    template_id: int,
    data: ProcesoTemplateUpdate,
    current_user: dict,
) -> ProcesoTemplate:
    template = obtener_template(db, template_id)
    # Contador solo puede editar templates que creó
    if current_user.get("rol") == "contador":
        if template.creado_por != current_user.get("empleado_id"):
            raise HTTPException(status_code=403, detail="Solo podés editar templates que vos creaste")

    for campo, valor in data.model_dump(exclude_none=True).items():
        setattr(template, campo, valor)
    db.commit()
    db.refresh(template)
    return template


def eliminar_template(db: Session, template_id: int) -> None:
    template = obtener_template(db, template_id)
    template.activo = False
    db.commit()


def obtener_pasos_template(db: Session, template_id: int) -> list[ProcesoPasoTemplate]:
    return (
        db.query(ProcesoPasoTemplate)
        .filter(ProcesoPasoTemplate.template_id == template_id)
        .order_by(ProcesoPasoTemplate.orden)
        .all()
    )


# ─── Pasos Template ───────────────────────────────────────────────────────────

def agregar_paso(db: Session, template_id: int, data: ProcesoPasoTemplateCreate) -> ProcesoPasoTemplate:
    obtener_template(db, template_id)  # valida existencia
    # Verificar que el orden no esté ocupado
    existente = db.query(ProcesoPasoTemplate).filter(
        ProcesoPasoTemplate.template_id == template_id,
        ProcesoPasoTemplate.orden == data.orden,
    ).first()
    if existente:
        raise HTTPException(status_code=409, detail=f"Ya existe un paso con orden {data.orden} en este template")

    paso = ProcesoPasoTemplate(**data.model_dump(), template_id=template_id)
    db.add(paso)
    db.commit()
    db.refresh(paso)
    return paso


def actualizar_paso(db: Session, paso_id: int, data: ProcesoPasoTemplateUpdate) -> ProcesoPasoTemplate:
    paso = db.query(ProcesoPasoTemplate).filter(ProcesoPasoTemplate.id == paso_id).first()
    if not paso:
        raise HTTPException(status_code=404, detail="Paso no encontrado")

    # Si se cambia el orden, verificar que no colisione
    if data.orden is not None and data.orden != paso.orden:
        colision = db.query(ProcesoPasoTemplate).filter(
            ProcesoPasoTemplate.template_id == paso.template_id,
            ProcesoPasoTemplate.orden == data.orden,
            ProcesoPasoTemplate.id != paso_id,
        ).first()
        if colision:
            raise HTTPException(status_code=409, detail=f"Ya existe un paso con orden {data.orden}")

    for campo, valor in data.model_dump(exclude_none=True).items():
        setattr(paso, campo, valor)
    db.commit()
    db.refresh(paso)
    return paso


def eliminar_paso(db: Session, paso_id: int) -> None:
    paso = db.query(ProcesoPasoTemplate).filter(ProcesoPasoTemplate.id == paso_id).first()
    if not paso:
        raise HTTPException(status_code=404, detail="Paso no encontrado")
    template_id = paso.template_id
    db.delete(paso)
    db.commit()
    _renumerar_pasos(db, template_id)


def _renumerar_pasos(db: Session, template_id: int) -> None:
    pasos = (
        db.query(ProcesoPasoTemplate)
        .filter(ProcesoPasoTemplate.template_id == template_id)
        .order_by(ProcesoPasoTemplate.orden)
        .all()
    )
    for i, paso in enumerate(pasos, start=1):
        paso.orden = i
    db.commit()


# ─── Instancias ───────────────────────────────────────────────────────────────

def crear_instancia(
    db: Session,
    data: ProcesoInstanciaCreate,
    current_user: dict,
) -> ProcesoInstancia:
    template = obtener_template(db, data.template_id)
    if not template.activo:
        raise HTTPException(status_code=400, detail="El template no está activo")

    if data.cliente_id:
        cliente = db.query(Cliente).filter(Cliente.id == data.cliente_id, Cliente.activo == True).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente no encontrado")

    if data.vencimiento_id:
        venc = db.query(Vencimiento).filter(Vencimiento.id == data.vencimiento_id).first()
        if not venc:
            raise HTTPException(status_code=404, detail="Vencimiento no encontrado")
        if data.cliente_id and venc.cliente_id != data.cliente_id:
            raise HTTPException(status_code=400, detail="El vencimiento no pertenece al cliente indicado")

    instancia = ProcesoInstancia(
        template_id=data.template_id,
        cliente_id=data.cliente_id,
        vencimiento_id=data.vencimiento_id,
        creado_por=current_user.get("empleado_id"),
    )
    db.add(instancia)
    db.flush()

    pasos = obtener_pasos_template(db, data.template_id)
    for paso_t in pasos:
        paso_i = ProcesoPasoInstancia(
            instancia_id=instancia.id,
            paso_template_id=paso_t.id,
            orden=paso_t.orden,
        )
        db.add(paso_i)

    db.commit()
    db.refresh(instancia)
    return instancia


def listar_instancias(
    db: Session,
    template_id: Optional[int] = None,
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoInstancia] = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ProcesoInstancia]:
    query = db.query(ProcesoInstancia)
    if template_id is not None:
        query = query.filter(ProcesoInstancia.template_id == template_id)
    if cliente_id is not None:
        query = query.filter(ProcesoInstancia.cliente_id == cliente_id)
    if estado is not None:
        query = query.filter(ProcesoInstancia.estado == estado)
    return query.order_by(ProcesoInstancia.created_at.desc()).offset(skip).limit(limit).all()


def obtener_instancia(db: Session, instancia_id: int) -> ProcesoInstancia:
    instancia = db.query(ProcesoInstancia).filter(ProcesoInstancia.id == instancia_id).first()
    if not instancia:
        raise HTTPException(status_code=404, detail="Instancia no encontrada")
    return instancia


def obtener_pasos_instancia(db: Session, instancia_id: int) -> list[ProcesoPasoInstancia]:
    return (
        db.query(ProcesoPasoInstancia)
        .filter(ProcesoPasoInstancia.instancia_id == instancia_id)
        .order_by(ProcesoPasoInstancia.orden)
        .all()
    )


def actualizar_instancia(db: Session, instancia_id: int, data: ProcesoInstanciaUpdate) -> ProcesoInstancia:
    instancia = obtener_instancia(db, instancia_id)
    if data.estado is not None:
        instancia.estado = data.estado
        if data.estado == EstadoInstancia.en_progreso and instancia.fecha_inicio is None:
            instancia.fecha_inicio = datetime.utcnow()
        if data.estado == EstadoInstancia.completado and instancia.fecha_fin is None:
            instancia.fecha_fin = datetime.utcnow()
    db.commit()
    db.refresh(instancia)
    return instancia


# ─── Pasos Instancia ──────────────────────────────────────────────────────────

def avanzar_paso_instancia(
    db: Session,
    paso_id: int,
    data: ProcesoPasoInstanciaUpdate,
    empleado_id: Optional[int] = None,
) -> ProcesoPasoInstancia:
    paso = db.query(ProcesoPasoInstancia).filter(ProcesoPasoInstancia.id == paso_id).first()
    if not paso:
        raise HTTPException(status_code=404, detail="Paso de instancia no encontrado")

    if data.estado is not None:
        _verificar_secuencialidad(db, paso, data.estado)
        _verificar_confirmacion_sop(db, paso, data.estado, empleado_id)

        if data.estado == EstadoPasoInstancia.en_progreso:
            if paso.fecha_inicio is None:
                paso.fecha_inicio = datetime.utcnow()

        if data.estado == EstadoPasoInstancia.completado:
            ahora = datetime.utcnow()
            paso.fecha_fin = ahora
            # Solo calcular tiempo si fecha_inicio fue registrado
            if paso.fecha_inicio is not None:
                paso.tiempo_real_minutos = (ahora - paso.fecha_inicio).total_seconds() / 60
            else:
                paso.tiempo_real_minutos = None

        paso.estado = data.estado

    if data.notas is not None:
        paso.notas = data.notas
    if data.asignado_a is not None:
        paso.asignado_a = data.asignado_a

    db.commit()
    db.refresh(paso)

    # Recalcular progreso de la instancia
    _recalcular_progreso(db, paso.instancia_id)

    return paso


def _verificar_confirmacion_sop(
    db: Session,
    paso: ProcesoPasoInstancia,
    nuevo_estado: EstadoPasoInstancia,
    empleado_id: Optional[int],
) -> None:
    """Si el proceso tiene SOP activo vinculado y el paso requiere confirmación de lectura, verificarla."""
    if nuevo_estado not in (EstadoPasoInstancia.en_progreso, EstadoPasoInstancia.completado):
        return
    if empleado_id is None:
        return

    try:
        from models.sop_documento import SopDocumento, SopPaso, EstadoSop
        from services.sop_asistido_service import verificar_confirmacion_lectura

        instancia = db.query(ProcesoInstancia).filter(
            ProcesoInstancia.id == paso.instancia_id
        ).first()
        if not instancia:
            return

        sop = (
            db.query(SopDocumento)
            .filter(
                SopDocumento.proceso_id == instancia.template_id,
                SopDocumento.estado == EstadoSop.activo,
            )
            .first()
        )
        if not sop:
            return

        sop_paso = (
            db.query(SopPaso)
            .filter(SopPaso.sop_id == sop.id, SopPaso.orden == paso.orden)
            .first()
        )
        if not sop_paso or not sop_paso.requiere_confirmacion_lectura:
            return

        tiene_confirmacion = verificar_confirmacion_lectura(db, sop_paso.id, empleado_id)
        if not tiene_confirmacion:
            raise HTTPException(
                status_code=409,
                detail="Este paso requiere que confirmes la lectura del SOP antes de avanzar.",
            )
    except HTTPException:
        raise
    except Exception:
        pass  # No bloquear el flujo por errores inesperados en la verificación


def _verificar_secuencialidad(
    db: Session,
    paso: ProcesoPasoInstancia,
    nuevo_estado: EstadoPasoInstancia,
) -> None:
    """Paso N no puede avanzar si el paso N-1 no está completado."""
    if nuevo_estado not in (EstadoPasoInstancia.en_progreso, EstadoPasoInstancia.completado):
        return
    if paso.orden <= 1:
        return

    paso_anterior = (
        db.query(ProcesoPasoInstancia)
        .filter(
            ProcesoPasoInstancia.instancia_id == paso.instancia_id,
            ProcesoPasoInstancia.orden == paso.orden - 1,
        )
        .first()
    )
    if paso_anterior and paso_anterior.estado != EstadoPasoInstancia.completado:
        raise HTTPException(
            status_code=422,
            detail=f"El paso {paso.orden - 1} debe estar completado antes de avanzar el paso {paso.orden}",
        )


def _recalcular_progreso(db: Session, instancia_id: int) -> None:
    """Recalcula progreso_pct y detecta si la instancia quedó completada."""
    pasos = obtener_pasos_instancia(db, instancia_id)
    if not pasos:
        return

    total = len(pasos)
    completados = sum(1 for p in pasos if p.estado == EstadoPasoInstancia.completado)
    progreso = completados / total

    instancia = db.query(ProcesoInstancia).filter(ProcesoInstancia.id == instancia_id).first()
    if not instancia:
        return

    instancia.progreso_pct = progreso

    if completados == total:
        instancia.estado = EstadoInstancia.completado
        if instancia.fecha_fin is None:
            instancia.fecha_fin = datetime.utcnow()
        _recalcular_estimados_template(db, instancia.template_id)
    elif completados > 0 and instancia.estado == EstadoInstancia.pendiente:
        instancia.estado = EstadoInstancia.en_progreso
        if instancia.fecha_inicio is None:
            instancia.fecha_inicio = datetime.utcnow()

    db.commit()


def _recalcular_estimados_template(db: Session, template_id: int) -> None:
    """
    Recalcula tiempo_estimado_minutos del template basado en instancias completadas.
    Solo se ejecuta si hay umbral_instancias_optimizador+ instancias completadas con datos reales.
    El umbral se lee de studio_config (configurable por estudio, default 5).
    """
    from models.studio_config import StudioConfig
    config = db.query(StudioConfig).first()
    UMBRAL = config.umbral_instancias_optimizador if config else 5
    try:
        instancias = (
            db.query(ProcesoInstancia)
            .filter(
                ProcesoInstancia.template_id == template_id,
                ProcesoInstancia.estado == EstadoInstancia.completado,
                ProcesoInstancia.fecha_inicio.isnot(None),
                ProcesoInstancia.fecha_fin.isnot(None),
            )
            .all()
        )
        if len(instancias) < UMBRAL:
            return

        tiempos = []
        for inst in instancias:
            delta = (inst.fecha_fin - inst.fecha_inicio).total_seconds() / 60
            if delta > 0:
                tiempos.append(delta)

        if not tiempos:
            return

        promedio = sum(tiempos) / len(tiempos)
        template = db.query(ProcesoTemplate).filter(ProcesoTemplate.id == template_id).first()
        if template:
            template.tiempo_estimado_minutos = int(promedio)
            db.commit()
    except Exception as exc:
        logger.warning(
            "proceso_service: no se pudo recalcular estimados del template %s — %s",
            template_id, exc,
        )
