from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth_dependencies import require_rol
from database import get_db
from models.sop_documento import AreaSop, EstadoSop
from schemas.automatizacion import AutomatizacionResponse
from schemas.sop import (
    ConfirmarLecturaResponse,
    GenerarSopRequest,
    SopDocumentoCreate,
    SopDocumentoResponse,
    SopDocumentoUpdate,
    SopPasoCreate,
    SopPasoResponse,
)
from services import sop_asistido_service

router = APIRouter(prefix="/api/sop", tags=["SOP Asistido"])


# ─── Generación asistida por IA (antes de /{id} para evitar conflicto de rutas) ─

@router.post("/generar-desde-descripcion", response_model=SopDocumentoResponse, status_code=201)
def generar_sop_desde_descripcion(
    data: GenerarSopRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Genera un SOP en estado borrador desde una descripción informal en lenguaje natural."""
    if not data.descripcion.strip():
        raise HTTPException(status_code=422, detail="La descripción es requerida")
    sop = sop_asistido_service.generar_sop_desde_descripcion(
        db,
        data.descripcion,
        data.area,
        current_user.get("empleado_id"),
    )
    return _sop_con_pasos_y_revisiones(db, sop)


# ─── Biblioteca (antes de /{id}) ──────────────────────────────────────────────

@router.get("/biblioteca")
def listar_biblioteca(
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo", "rrhh")),
):
    """Lista todos los SOPs activos con formato simplificado. Visible para todo el equipo."""
    return sop_asistido_service.listar_biblioteca(db)


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.post("", response_model=SopDocumentoResponse, status_code=201)
def crear_sop(
    data: SopDocumentoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Crea un SOP en estado borrador con sus pasos."""
    sop = sop_asistido_service.crear_sop(db, data, current_user.get("empleado_id"))
    return _sop_con_pasos_y_revisiones(db, sop)


@router.get("", response_model=list[SopDocumentoResponse])
def listar_sops(
    area: Optional[AreaSop] = None,
    estado: Optional[EstadoSop] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo", "rrhh")),
):
    """Lista SOPs con filtros opcionales. Activos visibles a todos; borradores/archivados solo al creador/responsable."""
    sops = sop_asistido_service.listar_sops_con_visibilidad(
        db,
        empleado_id=current_user.get("empleado_id"),
        area=area,
        estado=estado,
    )
    return [_sop_con_pasos_y_revisiones(db, s) for s in sops]


@router.get("/{sop_id}", response_model=SopDocumentoResponse)
def obtener_sop(
    sop_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo", "rrhh")),
):
    """Detalle de un SOP con pasos e historial de revisiones."""
    sop = sop_asistido_service.obtener_sop(db, sop_id)
    return _sop_con_pasos_y_revisiones(db, sop)


@router.patch("/{sop_id}", response_model=SopDocumentoResponse)
def actualizar_sop(
    sop_id: int,
    data: SopDocumentoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Actualiza campos del SOP."""
    sop = sop_asistido_service.actualizar_sop(db, sop_id, data)
    return _sop_con_pasos_y_revisiones(db, sop)


@router.post("/{sop_id}/pasos", response_model=SopPasoResponse, status_code=201)
def agregar_paso(
    sop_id: int,
    data: SopPasoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Agrega un paso al SOP."""
    return sop_asistido_service.agregar_paso_sop(db, sop_id, data)


@router.delete("/{sop_id}/pasos/{paso_id}", status_code=204)
def eliminar_paso(
    sop_id: int,
    paso_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Elimina un paso del SOP."""
    sop_asistido_service.eliminar_paso_sop(db, sop_id, paso_id)


@router.post("/{sop_id}/publicar", response_model=SopDocumentoResponse)
def publicar_sop(
    sop_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Cambia el estado de borrador a activo y registra revisión inicial."""
    sop = sop_asistido_service.publicar_sop(db, sop_id, current_user.get("empleado_id"))
    return _sop_con_pasos_y_revisiones(db, sop)


@router.post("/{sop_id}/archivar", response_model=SopDocumentoResponse)
def archivar_sop(
    sop_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """Cambia el estado a archivado."""
    sop = sop_asistido_service.archivar_sop(db, sop_id)
    return _sop_con_pasos_y_revisiones(db, sop)


# ─── Integración con automatizaciones ────────────────────────────────────────

@router.post("/{sop_id}/generar-automatizacion", response_model=AutomatizacionResponse, status_code=201)
def generar_automatizacion_desde_sop(
    sop_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno")),
):
    """Genera una automatización candidata desde los pasos automatizables del SOP."""
    aut = sop_asistido_service.generar_automatizacion_desde_sop(db, sop_id)
    return AutomatizacionResponse.model_validate(aut)


# ─── Confirmación de lectura ─────────────────────────────────────────────────

@router.post("/{sop_id}/pasos/{paso_id}/confirmar-lectura", response_model=ConfirmarLecturaResponse)
def confirmar_lectura(
    sop_id: int,
    paso_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo", "rrhh")),
):
    """Confirma la lectura de un paso del SOP. Si no requiere confirmación, responde 200 igualmente."""
    empleado_id = current_user.get("empleado_id")
    if not empleado_id:
        raise HTTPException(status_code=400, detail="Usuario sin empleado asociado")
    resultado = sop_asistido_service.confirmar_lectura(db, sop_id, paso_id, empleado_id)
    return resultado


# ─── Helper ───────────────────────────────────────────────────────────────────

def _sop_con_pasos_y_revisiones(db: Session, sop) -> SopDocumentoResponse:
    from schemas.sop import SopPasoResponse, SopRevisionResponse
    pasos = sop_asistido_service.obtener_pasos_sop(db, sop.id)
    revisiones = sop_asistido_service.obtener_revisiones_sop(db, sop.id)
    data = SopDocumentoResponse.model_validate(sop)
    data.pasos = [SopPasoResponse.model_validate(p) for p in pasos]
    data.revisiones = [SopRevisionResponse.model_validate(r) for r in revisiones]
    return data
