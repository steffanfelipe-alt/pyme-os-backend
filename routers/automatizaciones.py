from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, solo_dueno
from database import get_db
from schemas.automatizacion import (
    AutomatizacionResponse,
    AutomatizacionUpdate,
    DescartarRequest,
    GenerarFlujoRequest,
    GenerarFlujoResponse,
)
from services import automatizacion_service, proceso_service
from services.optimizador_service import (
    analizar_pasos_automatizabilidad,
    generar_flujo_n8n,
    _recalcular_ahorro,
)

router = APIRouter(prefix="/api/automatizaciones", tags=["Automatizaciones"])


@router.post("/generar", response_model=GenerarFlujoResponse, status_code=201)
async def generar_automatizacion(
    data: GenerarFlujoRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """
    Analiza los pasos de un template, genera el flujo n8n y persiste la automatización.
    """
    pasos = proceso_service.obtener_pasos_template(db, data.template_id, studio_id)
    pasos_dict = [
        {
            "orden": p.orden,
            "titulo": p.titulo,
            "descripcion": p.descripcion or "",
            "es_automatizable": p.es_automatizable,
        }
        for p in pasos
    ]

    analisis = await analizar_pasos_automatizabilidad(pasos_dict, db=db)
    flujo = await generar_flujo_n8n(pasos_dict, analisis, db=db)

    # Calcular ahorro propio como suma de minutos automatizables / 60
    pasos_automatizables = [p for p in pasos if p.es_automatizable]
    minutos_propios = sum(
        p.tiempo_estimado_minutos or 0 for p in pasos_automatizables
    )
    # Asume 20 ejecuciones mensuales como baseline
    ahorro_propio = (minutos_propios * 20) / 60

    ahorro_claude = analisis.get("ahorro_total_horas_mes", 0.0)
    ahorro_final = _recalcular_ahorro(ahorro_claude, ahorro_propio)

    automatizacion = automatizacion_service.crear_automatizacion(
        db=db,
        template_id=data.template_id,
        flujo_json=flujo,
        analisis_pasos=analisis,
        ahorro_horas_mes=ahorro_final,
        studio_id=studio_id,
    )

    return GenerarFlujoResponse(automatizacion=AutomatizacionResponse.model_validate(automatizacion))


@router.get("", response_model=list[AutomatizacionResponse])
def listar_automatizaciones(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    return automatizacion_service.listar_automatizaciones(db, studio_id)


@router.get("/pendientes", response_model=list[AutomatizacionResponse])
def listar_pendientes_revision(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Lista todas las automatizaciones pendientes de revisión."""
    return automatizacion_service.listar_pendientes_revision(db, studio_id)


@router.get("/{automatizacion_id}", response_model=AutomatizacionResponse)
def obtener_automatizacion(
    automatizacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    return automatizacion_service.obtener_automatizacion(db, automatizacion_id, studio_id)


@router.put("/{automatizacion_id}", response_model=AutomatizacionResponse)
def actualizar_automatizacion(
    automatizacion_id: int,
    data: AutomatizacionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    automatizacion_service.obtener_automatizacion(db, automatizacion_id, studio_id)  # access check
    return automatizacion_service.actualizar_automatizacion(db, automatizacion_id, data)


@router.delete("/{automatizacion_id}", status_code=204)
def eliminar_automatizacion(
    automatizacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    automatizacion_service.obtener_automatizacion(db, automatizacion_id, studio_id)  # access check
    automatizacion_service.eliminar_automatizacion(db, automatizacion_id)


@router.patch("/{automatizacion_id}/aprobar", response_model=AutomatizacionResponse)
def aprobar_automatizacion(
    automatizacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Aprueba una automatización y registra el timestamp de aprobación."""
    automatizacion_service.obtener_automatizacion(db, automatizacion_id, studio_id)  # access check
    return automatizacion_service.aprobar_automatizacion(db, automatizacion_id)


@router.patch("/{automatizacion_id}/descartar", response_model=AutomatizacionResponse)
def descartar_automatizacion(
    automatizacion_id: int,
    body: DescartarRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Descarta una automatización con motivo opcional."""
    automatizacion_service.obtener_automatizacion(db, automatizacion_id, studio_id)  # access check
    return automatizacion_service.descartar_automatizacion(db, automatizacion_id, body.motivo_descarte)
