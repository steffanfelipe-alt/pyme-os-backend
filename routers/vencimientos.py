from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol, solo_dueno, verificar_acceso_cliente
from database import get_db
from models.vencimiento import EstadoVencimiento
from schemas.vencimiento import VencimientoCreate, VencimientoResponse, VencimientoUpdate
from services import vencimiento_service

router = APIRouter(prefix="/api/vencimientos", tags=["Vencimientos"])


@router.patch("/{vencimiento_id}/cumplir", response_model=VencimientoResponse, response_model_exclude_none=True)
def cumplir_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    from schemas.vencimiento import VencimientoUpdate as VU
    return vencimiento_service.actualizar_vencimiento(
        db, vencimiento_id, VU(estado=EstadoVencimiento.cumplido), studio_id
    )


@router.post("", response_model=VencimientoResponse, status_code=201)
def crear_vencimiento(
    data: VencimientoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    if current_user.get("rol") == "contador":
        verificar_acceso_cliente(current_user, data.cliente_id, db)
    return vencimiento_service.crear_vencimiento(db, data, studio_id)


@router.get("", response_model=list[VencimientoResponse], response_model_exclude_none=True)
def listar_vencimientos(
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoVencimiento] = None,
    skip: int = 0,
    limit: int = 200,
    dias_max: Optional[int] = 180,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    if current_user.get("rol") == "contador" and cliente_id is not None:
        verificar_acceso_cliente(current_user, cliente_id, db)
    contador_id = current_user.get("empleado_id") if current_user.get("rol") == "contador" else None
    return vencimiento_service.listar_vencimientos(db, studio_id, cliente_id, estado, skip, limit, contador_id, dias_max)


@router.get("/{vencimiento_id}", response_model=VencimientoResponse, response_model_exclude_none=True)
def obtener_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return vencimiento_service.obtener_vencimiento(db, vencimiento_id, studio_id)


@router.put("/{vencimiento_id}", response_model=VencimientoResponse, response_model_exclude_none=True)
def actualizar_vencimiento(
    vencimiento_id: int,
    data: VencimientoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return vencimiento_service.actualizar_vencimiento(db, vencimiento_id, data, studio_id)


@router.delete("/{vencimiento_id}", status_code=204)
def eliminar_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    vencimiento_service.eliminar_vencimiento(db, vencimiento_id, studio_id)


@router.post("/{vencimiento_id}/crear-tarea", status_code=201)
def crear_tarea_desde_vencimiento(
    vencimiento_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Crea automáticamente una tarea a partir de un vencimiento pendiente."""
    from services.tarea_service import crear_tarea
    from schemas.tarea import TareaCreate
    from models.tarea import TipoTarea, PrioridadTarea

    venc = vencimiento_service.obtener_vencimiento(db, vencimiento_id, studio_id)
    dias = (venc.fecha_vencimiento - date.today()).days
    prioridad = PrioridadTarea.urgente if dias <= 3 else PrioridadTarea.alta if dias <= 7 else PrioridadTarea.normal

    tarea_data = TareaCreate(
        cliente_id=venc.cliente_id,
        titulo=f"{venc.tipo.value.upper()} — {venc.descripcion}",
        tipo=TipoTarea.declaracion,
        prioridad=prioridad,
        fecha_limite=venc.fecha_vencimiento,
    )
    tarea = crear_tarea(db, tarea_data, studio_id)
    return {"tarea_id": tarea.id, "titulo": tarea.titulo, "prioridad": tarea.prioridad}
