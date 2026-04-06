from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import require_rol, solo_dueno, verificar_acceso_cliente
from database import get_db
from models.proceso import EstadoInstancia
from schemas.proceso import (
    ProcesoInstanciaCreate,
    ProcesoInstanciaResponse,
    ProcesoInstanciaUpdate,
    ProcesoPasoInstanciaResponse,
    ProcesoPasoInstanciaUpdate,
    ProcesoPasoTemplateCreate,
    ProcesoPasoTemplateResponse,
    ProcesoPasoTemplateUpdate,
    ProcesoTemplateCreate,
    ProcesoTemplateResponse,
    ProcesoTemplateUpdate,
)
from services import proceso_service
from services.sop_service import generar_sop_pdf

router = APIRouter(prefix="/api/procesos", tags=["Procesos"])


# ─── Templates ────────────────────────────────────────────────────────────────

@router.post("/templates", status_code=201)
def crear_template(
    data: ProcesoTemplateCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    template = proceso_service.crear_template(db, data, current_user.get("empleado_id"))
    pasos = proceso_service.obtener_pasos_template(db, template.id)
    return ProcesoTemplateResponse.from_orm_with_pasos(template, pasos)


@router.get("/templates")
def listar_templates(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    templates = proceso_service.listar_templates(db)
    resultado = []
    for t in templates:
        pasos = proceso_service.obtener_pasos_template(db, t.id)
        resultado.append(ProcesoTemplateResponse.from_orm_with_pasos(t, pasos))
    return resultado


@router.get("/templates/{template_id}")
def obtener_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    template = proceso_service.obtener_template(db, template_id)
    pasos = proceso_service.obtener_pasos_template(db, template_id)
    return ProcesoTemplateResponse.from_orm_with_pasos(template, pasos)


@router.put("/templates/{template_id}")
def actualizar_template(
    template_id: int,
    data: ProcesoTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    template = proceso_service.actualizar_template(db, template_id, data, current_user)
    pasos = proceso_service.obtener_pasos_template(db, template_id)
    return ProcesoTemplateResponse.from_orm_with_pasos(template, pasos)


@router.delete("/templates/{template_id}", status_code=204)
def eliminar_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    proceso_service.eliminar_template(db, template_id)


# ─── Pasos Template ───────────────────────────────────────────────────────────

@router.post("/templates/{template_id}/pasos", response_model=ProcesoPasoTemplateResponse, status_code=201)
def agregar_paso(
    template_id: int,
    data: ProcesoPasoTemplateCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    return proceso_service.agregar_paso(db, template_id, data)


@router.put("/pasos-template/{paso_id}", response_model=ProcesoPasoTemplateResponse)
def actualizar_paso(
    paso_id: int,
    data: ProcesoPasoTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    return proceso_service.actualizar_paso(db, paso_id, data)


@router.delete("/pasos-template/{paso_id}", status_code=204)
def eliminar_paso(
    paso_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    proceso_service.eliminar_paso(db, paso_id)


# ─── Instancias ───────────────────────────────────────────────────────────────

@router.post("/instancias", response_model=ProcesoInstanciaResponse, status_code=201)
def crear_instancia(
    data: ProcesoInstanciaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    if data.cliente_id:
        verificar_acceso_cliente(current_user, data.cliente_id, db)
    instancia = proceso_service.crear_instancia(db, data, current_user)
    pasos = proceso_service.obtener_pasos_instancia(db, instancia.id)
    instancia.pasos = pasos
    return ProcesoInstanciaResponse.model_validate(instancia)


@router.get("/instancias", response_model=list[ProcesoInstanciaResponse])
def listar_instancias(
    template_id: Optional[int] = None,
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoInstancia] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    instancias = proceso_service.listar_instancias(db, template_id, cliente_id, estado, skip, limit)
    resultado = []
    for inst in instancias:
        pasos = proceso_service.obtener_pasos_instancia(db, inst.id)
        inst.pasos = pasos
        resultado.append(ProcesoInstanciaResponse.model_validate(inst))
    return resultado


@router.get("/instancias/{instancia_id}", response_model=ProcesoInstanciaResponse)
def obtener_instancia(
    instancia_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    instancia = proceso_service.obtener_instancia(db, instancia_id)
    pasos = proceso_service.obtener_pasos_instancia(db, instancia_id)

    # Enriquecer pasos con guia_sop si hay SOP activo vinculado al template
    sop_vinculado = None
    try:
        from services.sop_asistido_service import obtener_sop_activo_por_proceso, obtener_pasos_sop
        sop = obtener_sop_activo_por_proceso(db, instancia.template_id)
        if sop:
            sop_pasos = obtener_pasos_sop(db, sop.id)
            sop_pasos_por_orden = {p.orden: p.descripcion for p in sop_pasos}
            for paso in pasos:
                paso.guia_sop = sop_pasos_por_orden.get(paso.orden)

            sop_vinculado = {
                "id": sop.id,
                "titulo": sop.titulo,
                "area": sop.area.value,
                "descripcion_proposito": sop.descripcion_proposito,
                "resultado_esperado": sop.resultado_esperado,
                "pasos": [{"orden": p.orden, "descripcion": p.descripcion} for p in sop_pasos],
            }
    except Exception:
        pass

    instancia.pasos = pasos
    resp = ProcesoInstanciaResponse.model_validate(instancia)
    resp.sop_vinculado = sop_vinculado
    return resp


@router.put("/instancias/{instancia_id}", response_model=ProcesoInstanciaResponse)
def actualizar_instancia(
    instancia_id: int,
    data: ProcesoInstanciaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    instancia = proceso_service.actualizar_instancia(db, instancia_id, data)
    pasos = proceso_service.obtener_pasos_instancia(db, instancia_id)
    instancia.pasos = pasos
    return ProcesoInstanciaResponse.model_validate(instancia)


@router.put("/pasos-instancia/{paso_id}", response_model=ProcesoPasoInstanciaResponse)
def avanzar_paso_instancia(
    paso_id: int,
    data: ProcesoPasoInstanciaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    return proceso_service.avanzar_paso_instancia(db, paso_id, data, current_user.get("empleado_id"))


# ─── SOP ──────────────────────────────────────────────────────────────────────

@router.post("/templates/{template_id}/sop", status_code=201)
def generar_sop(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    ruta = generar_sop_pdf(db, template_id)
    return {"sop_url": ruta, "mensaje": "SOP generado exitosamente"}


# ─── Optimizador ─────────────────────────────────────────────────────────────

@router.post("/optimizar/desde-descripcion")
async def optimizar_desde_descripcion(
    payload: dict,
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    descripcion = payload.get("descripcion", "").strip()
    if not descripcion:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="El campo 'descripcion' es requerido")
    from services.optimizador_service import optimizar_descripcion
    return await optimizar_descripcion(descripcion)


@router.post("/templates/{template_id}/analizar-automatizabilidad")
async def analizar_automatizabilidad(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    from services.optimizador_service import analizar_pasos_automatizabilidad
    pasos = proceso_service.obtener_pasos_template(db, template_id)
    pasos_dict = [
        {
            "orden": p.orden,
            "titulo": p.titulo,
            "descripcion": p.descripcion or "",
        }
        for p in pasos
    ]
    return await analizar_pasos_automatizabilidad(pasos_dict)
