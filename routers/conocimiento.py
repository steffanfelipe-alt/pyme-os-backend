# Router separado de routers/procesos.py porque los SOPs son documentos de conocimiento
# organizacional, no operaciones de proceso. La separación permite que el frontend
# tenga un endpoint limpio para la "base de conocimiento" sin mezclar con CRUD operativo.
# Si en el futuro se agregan wikis, playbooks o FAQs, van aquí también.

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import require_rol
from database import get_db
from schemas.proceso import ProcesoTemplateResponse
from services import proceso_service

router = APIRouter(prefix="/api/conocimiento", tags=["Conocimiento"])


@router.get("/sops")
def listar_sops(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Lista todos los templates que tienen SOP generado."""
    templates = proceso_service.listar_templates(db)
    resultado = []
    for t in templates:
        if t.sop_url:
            pasos = proceso_service.obtener_pasos_template(db, t.id)
            resultado.append(ProcesoTemplateResponse.from_orm_with_pasos(t, pasos))
    return resultado


@router.get("/sops/{template_id}")
def obtener_sop(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Retorna el template con su SOP generado."""
    template = proceso_service.obtener_template(db, template_id)
    if not template.sop_url:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Este template no tiene SOP generado")
    pasos = proceso_service.obtener_pasos_template(db, template_id)
    return ProcesoTemplateResponse.from_orm_with_pasos(template, pasos)
