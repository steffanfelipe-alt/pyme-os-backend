"""
Servicio del módulo SOP Asistido.
CRUD + generación con IA + integración con automatizaciones.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import anthropic
from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.ai_client import get_anthropic_client

from models.proceso import Automatizacion, EstadoRevisionAutomatizacion, ProcesoTemplate
from models.sop_documento import (
    AreaSop, EstadoSop,
    SopConfirmacionLectura, SopDocumento, SopPaso, SopRevision,
)
from schemas.sop import SopDocumentoCreate, SopDocumentoUpdate, SopPasoCreate

logger = logging.getLogger("pymeos")

_MODELO = "claude-haiku-4-5-20251001"

_SYSTEM_PROMPT_SOP = (
    "Sos un asistente especializado en documentar procedimientos para estudios contables argentinos. "
    "Tu tarea es tomar una descripción informal de cómo se hace algo en el estudio y convertirla en un SOP estructurado. "
    "Respondé SIEMPRE con un objeto JSON válido y nada más, sin texto adicional, sin comillas de markdown."
)


def _limpiar_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ─── CRUD básico ──────────────────────────────────────────────────────────────

def crear_sop(db: Session, data: SopDocumentoCreate, empleado_id: Optional[int], studio_id: int = None) -> SopDocumento:
    sop = SopDocumento(
        studio_id=studio_id,
        titulo=data.titulo,
        area=data.area,
        descripcion_proposito=data.descripcion_proposito,
        resultado_esperado=data.resultado_esperado,
        empleado_creador_id=empleado_id,
        empleado_responsable_id=data.empleado_responsable_id,
        proceso_id=data.proceso_id,
        estado=EstadoSop.borrador,
    )
    db.add(sop)
    db.flush()

    for paso_data in data.pasos:
        paso = SopPaso(
            sop_id=sop.id,
            orden=paso_data.orden,
            descripcion=paso_data.descripcion,
            responsable_sugerido=paso_data.responsable_sugerido,
            tiempo_estimado_minutos=paso_data.tiempo_estimado_minutos,
            recursos=paso_data.recursos,
            es_automatizable=paso_data.es_automatizable,
            requiere_confirmacion_lectura=paso_data.requiere_confirmacion_lectura,
        )
        db.add(paso)

    db.commit()
    db.refresh(sop)
    return sop


def listar_sops(
    db: Session,
    area: Optional[AreaSop] = None,
    estado: Optional[EstadoSop] = None,
    empleado_id: Optional[int] = None,
    studio_id: int = None,
) -> list[SopDocumento]:
    query = db.query(SopDocumento)
    if studio_id is not None:
        query = query.filter(SopDocumento.studio_id == studio_id)
    if area is not None:
        query = query.filter(SopDocumento.area == area)
    if estado is not None:
        query = query.filter(SopDocumento.estado == estado)
    # Visibility: activos visible to all; borradores/archivados only to creator/responsable
    if estado != EstadoSop.activo and empleado_id is not None:
        query = query.filter(
            (SopDocumento.estado == EstadoSop.activo)
            | (SopDocumento.empleado_creador_id == empleado_id)
            | (SopDocumento.empleado_responsable_id == empleado_id)
        )
    return query.order_by(SopDocumento.updated_at.desc()).all()


def listar_sops_con_visibilidad(
    db: Session,
    empleado_id: Optional[int],
    area: Optional[AreaSop] = None,
    estado: Optional[EstadoSop] = None,
    studio_id: int = None,
) -> list[SopDocumento]:
    """Aplica reglas de visibilidad: activos visible a todos; borradores/archivados solo a creador/responsable."""
    query = db.query(SopDocumento)
    if studio_id is not None:
        query = query.filter(SopDocumento.studio_id == studio_id)
    if area is not None:
        query = query.filter(SopDocumento.area == area)

    if estado is not None:
        # Filtro explícito de estado + visibilidad
        if estado == EstadoSop.activo:
            query = query.filter(SopDocumento.estado == EstadoSop.activo)
        else:
            query = query.filter(
                SopDocumento.estado == estado,
                (SopDocumento.empleado_creador_id == empleado_id)
                | (SopDocumento.empleado_responsable_id == empleado_id),
            )
    else:
        # Sin filtro de estado: activos para todos + propios borradores/archivados
        if empleado_id is not None:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    SopDocumento.estado == EstadoSop.activo,
                    SopDocumento.empleado_creador_id == empleado_id,
                    SopDocumento.empleado_responsable_id == empleado_id,
                )
            )
        else:
            query = query.filter(SopDocumento.estado == EstadoSop.activo)

    return query.order_by(SopDocumento.updated_at.desc()).all()


def obtener_sop(db: Session, sop_id: int) -> SopDocumento:
    sop = db.query(SopDocumento).filter(SopDocumento.id == sop_id).first()
    if not sop:
        raise HTTPException(status_code=404, detail="SOP no encontrado")
    return sop


def obtener_pasos_sop(db: Session, sop_id: int) -> list[SopPaso]:
    return (
        db.query(SopPaso)
        .filter(SopPaso.sop_id == sop_id)
        .order_by(SopPaso.orden)
        .all()
    )


def obtener_revisiones_sop(db: Session, sop_id: int) -> list[SopRevision]:
    return (
        db.query(SopRevision)
        .filter(SopRevision.sop_id == sop_id)
        .order_by(SopRevision.created_at.desc())
        .all()
    )


def actualizar_sop(db: Session, sop_id: int, data: SopDocumentoUpdate) -> SopDocumento:
    sop = obtener_sop(db, sop_id)
    for campo, valor in data.model_dump(exclude_none=True).items():
        setattr(sop, campo, valor)
    db.commit()
    db.refresh(sop)
    return sop


def agregar_paso_sop(db: Session, sop_id: int, data: SopPasoCreate) -> SopPaso:
    obtener_sop(db, sop_id)
    paso = SopPaso(
        sop_id=sop_id,
        orden=data.orden,
        descripcion=data.descripcion,
        responsable_sugerido=data.responsable_sugerido,
        tiempo_estimado_minutos=data.tiempo_estimado_minutos,
        recursos=data.recursos,
        es_automatizable=data.es_automatizable,
        requiere_confirmacion_lectura=data.requiere_confirmacion_lectura,
    )
    db.add(paso)
    db.commit()
    db.refresh(paso)
    return paso


def eliminar_paso_sop(db: Session, sop_id: int, paso_id: int) -> None:
    obtener_sop(db, sop_id)
    paso = db.query(SopPaso).filter(SopPaso.id == paso_id, SopPaso.sop_id == sop_id).first()
    if not paso:
        raise HTTPException(status_code=404, detail="Paso no encontrado en este SOP")
    db.delete(paso)
    db.commit()


def publicar_sop(db: Session, sop_id: int, empleado_id: Optional[int]) -> SopDocumento:
    sop = obtener_sop(db, sop_id)
    if sop.estado == EstadoSop.activo:
        raise HTTPException(status_code=400, detail="El SOP ya está activo")
    sop.estado = EstadoSop.activo
    ahora = datetime.utcnow()
    sop.fecha_ultima_revision = ahora

    revision = SopRevision(
        sop_id=sop_id,
        fecha_revision=ahora,
        descripcion_cambio="Publicación inicial",
        empleado_id=empleado_id,
        version_resultante=sop.version,
    )
    db.add(revision)
    db.commit()
    db.refresh(sop)
    return sop


def archivar_sop(db: Session, sop_id: int) -> SopDocumento:
    sop = obtener_sop(db, sop_id)
    sop.estado = EstadoSop.archivado
    db.commit()
    db.refresh(sop)
    return sop


# ─── Generación asistida por IA ───────────────────────────────────────────────

async def generar_sop_desde_descripcion(
    db: Session,
    descripcion: str,
    area: Optional[AreaSop],
    empleado_id: Optional[int],
    studio_id: int = None,
) -> SopDocumento:
    prompt = (
        f'El JSON debe tener esta estructura exacta: {{'
        f'"titulo": string, '
        f'"area": uno de [administracion, impuestos, laboral, atencion_cliente, rrhh, otro], '
        f'"descripcion_proposito": "string de 1-2 oraciones", '
        f'"resultado_esperado": "string de 1 oración", '
        f'"pasos": [{{"orden": number, "descripcion": string, '
        f'"responsable_sugerido": string o null, '
        f'"tiempo_estimado_minutos": number o null, '
        f'"es_automatizable": boolean}}]'
        f'}}. Mantené los pasos simples y accionables. No inventes información que no esté en la descripción.'
        f'\n\nDescripción del proceso:\n{descripcion}'
    )

    client = get_anthropic_client(db)
    mensaje = await client.messages.create(
        model=_MODELO,
        max_tokens=1024,
        system=_SYSTEM_PROMPT_SOP,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = mensaje.content[0].text

    try:
        datos = _limpiar_json(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"La IA devolvió una respuesta que no es JSON válido: {exc}",
        )

    # Usar área de la request si se proveyó, de lo contrario la del JSON
    area_final_str = (area.value if area else datos.get("area", "otro"))
    try:
        area_final = AreaSop(area_final_str)
    except ValueError:
        area_final = AreaSop.otro

    pasos_raw = datos.get("pasos", [])
    pasos_create = [
        SopPasoCreate(
            orden=p.get("orden", i + 1),
            descripcion=p.get("descripcion", ""),
            responsable_sugerido=p.get("responsable_sugerido"),
            tiempo_estimado_minutos=p.get("tiempo_estimado_minutos"),
            es_automatizable=bool(p.get("es_automatizable", False)),
        )
        for i, p in enumerate(pasos_raw)
    ]

    doc_data = SopDocumentoCreate(
        titulo=datos.get("titulo", "SOP generado por IA"),
        area=area_final,
        descripcion_proposito=datos.get("descripcion_proposito"),
        resultado_esperado=datos.get("resultado_esperado"),
        pasos=pasos_create,
    )
    return crear_sop(db, doc_data, empleado_id, studio_id)


# ─── Integración con automatizaciones ─────────────────────────────────────────

async def generar_automatizacion_desde_sop(db: Session, sop_id: int) -> Automatizacion:
    sop = obtener_sop(db, sop_id)
    pasos = obtener_pasos_sop(db, sop_id)

    pasos_automatizables = [p for p in pasos if p.es_automatizable]
    if not pasos_automatizables:
        raise HTTPException(
            status_code=400,
            detail="Este SOP no tiene pasos marcados como automatizables",
        )

    if not sop.proceso_id:
        raise HTTPException(
            status_code=400,
            detail="El SOP debe estar vinculado a un proceso para generar una automatización",
        )

    template = db.query(ProcesoTemplate).filter(ProcesoTemplate.id == sop.proceso_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="Proceso vinculado no encontrado")

    # Reutilizar el servicio del optimizador para generar el flujo
    from services.optimizador_service import analizar_pasos_automatizabilidad, generar_flujo_n8n, _recalcular_ahorro

    pasos_dict = [
        {
            "orden": p.orden,
            "titulo": p.descripcion[:80],
            "descripcion": p.descripcion,
            "es_automatizable": p.es_automatizable,
            "automatizabilidad": "si" if p.es_automatizable else "no",
        }
        for p in pasos
    ]

    analisis = await analizar_pasos_automatizabilidad(pasos_dict)
    flujo = await generar_flujo_n8n(pasos_dict, analisis)

    minutos_propios = sum(p.tiempo_estimado_minutos or 0 for p in pasos_automatizables)
    ahorro_propio = (minutos_propios * 20) / 60
    ahorro_claude = analisis.get("ahorro_total_horas_mes", 0.0)
    ahorro_final = _recalcular_ahorro(ahorro_claude, ahorro_propio)

    # Buscar o crear automatización para el template
    existente = db.query(Automatizacion).filter(
        Automatizacion.template_id == sop.proceso_id
    ).first()

    if existente:
        existente.flujo_json = flujo
        existente.analisis_pasos = analisis
        existente.ahorro_horas_mes = ahorro_final
        existente.estado_revision = EstadoRevisionAutomatizacion.pendiente
        db.commit()
        db.refresh(existente)
        return existente

    aut = Automatizacion(
        template_id=sop.proceso_id,
        flujo_json=flujo,
        analisis_pasos=analisis,
        ahorro_horas_mes=ahorro_final,
        estado_revision=EstadoRevisionAutomatizacion.pendiente,
    )
    db.add(aut)
    db.commit()
    db.refresh(aut)
    return aut


# ─── Biblioteca ───────────────────────────────────────────────────────────────

def listar_biblioteca(db: Session, studio_id: int = None) -> list[dict]:
    from models.empleado import Empleado

    filtros = [SopDocumento.estado == EstadoSop.activo]
    if studio_id is not None:
        filtros.append(SopDocumento.studio_id == studio_id)
    sops = (
        db.query(SopDocumento)
        .filter(*filtros)
        .order_by(SopDocumento.titulo)
        .all()
    )

    emp_filtros = [Empleado.activo == True]
    if studio_id is not None:
        emp_filtros.append(Empleado.studio_id == studio_id)
    empleados_idx = {e.id: e.nombre for e in db.query(Empleado).filter(*emp_filtros).all()}
    tmpl_filtros = [ProcesoTemplate.activo == True]
    if studio_id is not None:
        tmpl_filtros.append(ProcesoTemplate.studio_id == studio_id)
    templates_idx = {
        t.id: {"id": t.id, "nombre": t.nombre}
        for t in db.query(ProcesoTemplate).filter(*tmpl_filtros).all()
    }

    resultado = []
    for sop in sops:
        pasos = obtener_pasos_sop(db, sop.id)
        resultado.append({
            "id": sop.id,
            "titulo": sop.titulo,
            "area": sop.area.value,
            "descripcion_proposito": sop.descripcion_proposito,
            "resultado_esperado": sop.resultado_esperado,
            "responsable_nombre": empleados_idx.get(sop.empleado_responsable_id) if sop.empleado_responsable_id else None,
            "fecha_ultima_revision": sop.fecha_ultima_revision.isoformat() if sop.fecha_ultima_revision else None,
            "cantidad_pasos": len(pasos),
            "pasos": [
                {
                    "id": p.id,
                    "sop_id": p.sop_id,
                    "orden": p.orden,
                    "descripcion": p.descripcion,
                    "responsable_sugerido": p.responsable_sugerido,
                    "tiempo_estimado_minutos": p.tiempo_estimado_minutos,
                    "recursos": p.recursos,
                    "es_automatizable": p.es_automatizable,
                    "requiere_confirmacion_lectura": p.requiere_confirmacion_lectura,
                    "created_at": p.created_at.isoformat(),
                }
                for p in pasos
            ],
            "proceso_vinculado": templates_idx.get(sop.proceso_id) if sop.proceso_id else None,
        })

    return resultado


# ─── Confirmación de lectura ──────────────────────────────────────────────────

def confirmar_lectura(
    db: Session,
    sop_id: int,
    paso_id: int,
    empleado_id: int,
    proceso_instancia_paso_id: Optional[int] = None,
) -> dict:
    obtener_sop(db, sop_id)
    paso = db.query(SopPaso).filter(SopPaso.id == paso_id, SopPaso.sop_id == sop_id).first()
    if not paso:
        raise HTTPException(status_code=404, detail="Paso no encontrado en este SOP")

    if not paso.requiere_confirmacion_lectura:
        return {"confirmado": True, "mensaje": "Este paso no requiere confirmación de lectura", "requiere_confirmacion": False}

    # Verificar si ya existe confirmación reciente (últimos 30 días)
    hace_30_dias = datetime.utcnow() - timedelta(days=30)
    confirmacion_reciente = (
        db.query(SopConfirmacionLectura)
        .filter(
            SopConfirmacionLectura.sop_paso_id == paso_id,
            SopConfirmacionLectura.empleado_id == empleado_id,
            SopConfirmacionLectura.fecha_confirmacion >= hace_30_dias,
        )
        .first()
    )

    if confirmacion_reciente:
        return {"confirmado": True, "mensaje": "Ya confirmaste la lectura de este paso recientemente", "requiere_confirmacion": True}

    confirmacion = SopConfirmacionLectura(
        sop_paso_id=paso_id,
        empleado_id=empleado_id,
        proceso_instancia_paso_id=proceso_instancia_paso_id,
        fecha_confirmacion=datetime.utcnow(),
    )
    db.add(confirmacion)
    db.commit()
    return {"confirmado": True, "mensaje": "Confirmación de lectura registrada", "requiere_confirmacion": True}


def verificar_confirmacion_lectura(
    db: Session,
    sop_paso_id: int,
    empleado_id: int,
) -> bool:
    """Retorna True si el empleado tiene confirmación de lectura vigente (últimos 30 días)."""
    hace_30_dias = datetime.utcnow() - timedelta(days=30)
    return db.query(SopConfirmacionLectura).filter(
        SopConfirmacionLectura.sop_paso_id == sop_paso_id,
        SopConfirmacionLectura.empleado_id == empleado_id,
        SopConfirmacionLectura.fecha_confirmacion >= hace_30_dias,
    ).first() is not None


def obtener_sop_activo_por_proceso(db: Session, proceso_id: int) -> Optional[SopDocumento]:
    """Retorna el SOP activo más reciente vinculado al proceso, o None."""
    return (
        db.query(SopDocumento)
        .filter(
            SopDocumento.proceso_id == proceso_id,
            SopDocumento.estado == EstadoSop.activo,
        )
        .order_by(SopDocumento.fecha_ultima_revision.desc().nullslast())
        .first()
    )
