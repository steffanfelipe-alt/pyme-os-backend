# Router del Centro de Conocimientos — biblioteca de SOPs publicados, automatizaciones
# aprobadas y automatizaciones Python. Separado del CRUD operativo para que el frontend
# tenga endpoints limpios orientados a consulta y búsqueda.

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import require_rol
from database import get_db
from schemas.proceso import ProcesoTemplateResponse
from services import proceso_service

router = APIRouter(prefix="/api/conocimiento", tags=["Conocimiento"])


# ─── SOPs ─────────────────────────────────────────────────────────────────────

@router.get("/sops")
def listar_sops(
    q: Optional[str] = None,
    area: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Lista todos los templates que tienen SOP generado. Soporta búsqueda por q y filtro por área."""
    from models.sop_documento import SopDocumento, EstadoSop, AreaSop
    from sqlalchemy.orm import Session as _S

    # SOPs asistidos publicados (SopDocumento con estado activo)
    query = db.query(SopDocumento).filter(SopDocumento.estado == EstadoSop.activo)

    if area:
        try:
            area_enum = AreaSop(area)
            query = query.filter(SopDocumento.area == area_enum)
        except ValueError:
            pass

    sops = query.order_by(SopDocumento.updated_at.desc()).all()

    resultado = []
    for sop in sops:
        if q:
            texto = f"{sop.titulo} {sop.descripcion_proposito or ''} {sop.resultado_esperado or ''}"
            if q.lower() not in texto.lower():
                continue
        resultado.append({
            "id": sop.id,
            "tipo": "sop",
            "titulo": sop.titulo,
            "area": sop.area.value if sop.area else None,
            "descripcion_proposito": sop.descripcion_proposito,
            "resultado_esperado": sop.resultado_esperado,
            "version": sop.version,
            "proceso_template_id": sop.proceso_id,
            "updated_at": sop.updated_at.isoformat() if sop.updated_at else None,
        })

    # También incluir templates con sop_url (PDF generado)
    templates = proceso_service.listar_templates(db)
    for t in templates:
        if not t.sop_url:
            continue
        if q and q.lower() not in (t.nombre + " " + (t.descripcion or "")).lower():
            continue
        resultado.append({
            "id": f"template_{t.id}",
            "tipo": "sop_pdf",
            "titulo": t.nombre,
            "area": None,
            "descripcion_proposito": t.descripcion,
            "resultado_esperado": None,
            "version": t.sop_version,
            "proceso_template_id": t.id,
            "sop_url": t.sop_url,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        })

    return resultado


@router.get("/sops/{sop_id}")
def obtener_sop(
    sop_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Retorna un SOP publicado con sus pasos."""
    from fastapi import HTTPException
    from models.sop_documento import SopDocumento, SopPaso

    sop = db.query(SopDocumento).filter(SopDocumento.id == sop_id).first()
    if not sop:
        raise HTTPException(status_code=404, detail="SOP no encontrado")

    pasos = db.query(SopPaso).filter(SopPaso.sop_id == sop_id).order_by(SopPaso.orden).all()

    return {
        "id": sop.id,
        "titulo": sop.titulo,
        "area": sop.area.value if sop.area else None,
        "descripcion_proposito": sop.descripcion_proposito,
        "resultado_esperado": sop.resultado_esperado,
        "version": sop.version,
        "proceso_template_id": sop.proceso_id,
        "pasos": [
            {
                "orden": p.orden,
                "descripcion": p.descripcion,
                "responsable_sugerido": p.responsable_sugerido,
                "tiempo_estimado_minutos": p.tiempo_estimado_minutos,
                "es_automatizable": p.es_automatizable,
            }
            for p in pasos
        ],
        "updated_at": sop.updated_at.isoformat() if sop.updated_at else None,
    }


# ─── Automatizaciones n8n aprobadas ───────────────────────────────────────────

@router.get("/automatizaciones")
def listar_automatizaciones_aprobadas(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Lista automatizaciones n8n aprobadas, con JSON de flujo y template asociado."""
    from models.proceso import Automatizacion, EstadoRevisionAutomatizacion, ProcesoTemplate

    autos = (
        db.query(Automatizacion)
        .filter(Automatizacion.estado_revision == EstadoRevisionAutomatizacion.aprobada)
        .order_by(Automatizacion.aprobado_at.desc())
        .all()
    )

    template_ids = {a.template_id for a in autos if a.template_id}
    templates_map = {
        t.id: t.nombre
        for t in db.query(ProcesoTemplate).filter(ProcesoTemplate.id.in_(template_ids)).all()
    } if template_ids else {}

    resultado = []
    for auto in autos:
        nombre = templates_map.get(auto.template_id, f"Automatización #{auto.id}")
        if q and q.lower() not in nombre.lower():
            continue
        resultado.append({
            "id": auto.id,
            "tipo": "automatizacion_n8n",
            "nombre": nombre,
            "template_id": auto.template_id,
            "herramienta": auto.herramienta or "n8n",
            "ahorro_horas_mes": auto.ahorro_horas_mes,
            "flujo_json": auto.flujo_json,
            "aprobado_at": auto.aprobado_at.isoformat() if auto.aprobado_at else None,
        })

    return resultado


# ─── Automatizaciones Python ───────────────────────────────────────────────────

@router.get("/automatizaciones-python")
def listar_automatizaciones_python(
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Lista automatizaciones Python activas del centro de conocimientos."""
    from models.automatizacion_python import AutomatizacionPython, EstadoAutomatizacionPython

    autos = (
        db.query(AutomatizacionPython)
        .filter(AutomatizacionPython.estado == EstadoAutomatizacionPython.activo)
        .order_by(AutomatizacionPython.updated_at.desc())
        .all()
    )

    resultado = []
    for auto in autos:
        if q and q.lower() not in (auto.nombre + " " + (auto.descripcion or "")).lower():
            continue
        resultado.append({
            "id": auto.id,
            "tipo": "automatizacion_python",
            "nombre": auto.nombre,
            "descripcion": auto.descripcion,
            "nodos_count": len(auto.nodos or []),
            "tiene_codigo": bool(auto.codigo_generado),
            "updated_at": auto.updated_at.isoformat() if auto.updated_at else None,
        })

    return resultado


# ─── Búsqueda unificada ────────────────────────────────────────────────────────

@router.get("/buscar")
def buscar_conocimiento(
    q: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """
    Búsqueda full-text entre SOPs, automatizaciones n8n y automatizaciones Python.
    Retorna resultados unificados con tipo, id, titulo/nombre y descripcion.
    """
    if not q or len(q) < 2:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="La búsqueda debe tener al menos 2 caracteres.")

    resultados = []

    # SOPs asistidos
    from models.sop_documento import SopDocumento, EstadoSop
    sops = db.query(SopDocumento).filter(SopDocumento.estado == EstadoSop.activo).all()
    for sop in sops:
        texto = f"{sop.titulo} {sop.descripcion_proposito or ''} {sop.resultado_esperado or ''}"
        if q.lower() in texto.lower():
            resultados.append({
                "tipo": "sop",
                "id": sop.id,
                "titulo": sop.titulo,
                "descripcion": sop.descripcion_proposito,
                "area": sop.area.value if sop.area else None,
                "updated_at": sop.updated_at.isoformat() if sop.updated_at else None,
            })

    # Automatizaciones n8n aprobadas
    from models.proceso import Automatizacion, EstadoRevisionAutomatizacion, ProcesoTemplate
    autos = db.query(Automatizacion).filter(
        Automatizacion.estado_revision == EstadoRevisionAutomatizacion.aprobada
    ).all()
    template_ids = {a.template_id for a in autos if a.template_id}
    templates_map = {
        t.id: t.nombre
        for t in db.query(ProcesoTemplate).filter(ProcesoTemplate.id.in_(template_ids)).all()
    } if template_ids else {}
    for auto in autos:
        nombre = templates_map.get(auto.template_id, f"Automatización #{auto.id}")
        if q.lower() in nombre.lower():
            resultados.append({
                "tipo": "automatizacion_n8n",
                "id": auto.id,
                "titulo": nombre,
                "descripcion": None,
                "herramienta": auto.herramienta or "n8n",
                "ahorro_horas_mes": auto.ahorro_horas_mes,
                "updated_at": auto.aprobado_at.isoformat() if auto.aprobado_at else None,
            })

    # Automatizaciones Python
    from models.automatizacion_python import AutomatizacionPython, EstadoAutomatizacionPython
    py_autos = db.query(AutomatizacionPython).filter(
        AutomatizacionPython.estado == EstadoAutomatizacionPython.activo
    ).all()
    for auto in py_autos:
        texto = f"{auto.nombre} {auto.descripcion or ''}"
        if q.lower() in texto.lower():
            resultados.append({
                "tipo": "automatizacion_python",
                "id": auto.id,
                "titulo": auto.nombre,
                "descripcion": auto.descripcion,
                "nodos_count": len(auto.nodos or []),
                "updated_at": auto.updated_at.isoformat() if auto.updated_at else None,
            })

    return {"query": q, "total": len(resultados), "resultados": resultados}
