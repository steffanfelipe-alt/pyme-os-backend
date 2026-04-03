from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import solo_dueno
from database import get_db
from schemas.automatizacion import (
    AutomatizacionResponse,
    AutomatizacionUpdate,
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
def generar_automatizacion(
    data: GenerarFlujoRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Analiza los pasos de un template, genera el flujo n8n y persiste la automatización.
    """
    pasos = proceso_service.obtener_pasos_template(db, data.template_id)
    pasos_dict = [
        {
            "orden": p.orden,
            "titulo": p.titulo,
            "descripcion": p.descripcion or "",
            "es_automatizable": p.es_automatizable,
        }
        for p in pasos
    ]

    analisis = analizar_pasos_automatizabilidad(pasos_dict)
    flujo = generar_flujo_n8n(pasos_dict, analisis)

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
    )

    return GenerarFlujoResponse(automatizacion=AutomatizacionResponse.model_validate(automatizacion))


@router.get("", response_model=list[AutomatizacionResponse])
def listar_automatizaciones(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    return automatizacion_service.listar_automatizaciones(db)


@router.get("/{automatizacion_id}", response_model=AutomatizacionResponse)
def obtener_automatizacion(
    automatizacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    return automatizacion_service.obtener_automatizacion(db, automatizacion_id)


@router.put("/{automatizacion_id}", response_model=AutomatizacionResponse)
def actualizar_automatizacion(
    automatizacion_id: int,
    data: AutomatizacionUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    return automatizacion_service.actualizar_automatizacion(db, automatizacion_id, data)


@router.delete("/{automatizacion_id}", status_code=204)
def eliminar_automatizacion(
    automatizacion_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    automatizacion_service.eliminar_automatizacion(db, automatizacion_id)
