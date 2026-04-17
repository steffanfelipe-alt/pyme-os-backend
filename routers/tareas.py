from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol, solo_dueno
from database import get_db
from models.tarea import EstadoTarea, PrioridadTarea
from schemas.tarea import CuadranteEisenhower, PrioridadEisenhowerUpdate, TareaCreate, TareaResponse, TareaUpdate
from services import tarea_service

router = APIRouter(prefix="/api/tareas", tags=["Tareas"])

_ROL_TAREA = require_rol("dueno", "contador", "administrativo")


@router.post("", response_model=TareaResponse, status_code=201)
def crear_tarea(
    data: TareaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return tarea_service.crear_tarea(db, data, studio_id)


@router.get("", response_model=list[TareaResponse], response_model_exclude_none=True)
def listar_tareas(
    cliente_id: Optional[int] = None,
    empleado_id: Optional[int] = None,
    estado: Optional[EstadoTarea] = None,
    prioridad: Optional[PrioridadTarea] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    # Contador solo ve sus propias tareas
    if current_user.get("rol") == "contador":
        empleado_id = current_user.get("empleado_id")
    return tarea_service.listar_tareas(db, studio_id, cliente_id, empleado_id, estado, prioridad, skip, limit)


# ─── Eisenhower — deben ir ANTES de /{tarea_id} para no ser capturadas ────────

@router.get("/matriz-eisenhower", response_model=CuadranteEisenhower)
def get_matriz_eisenhower(
    empleado_id: Optional[int] = None,
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL_TAREA),
    studio_id: int = Depends(get_studio_id),
):
    """Clasifica tareas activas en cuadrantes Eisenhower. Excluye completadas."""
    return tarea_service.get_matriz_eisenhower(db, studio_id, empleado_id, cliente_id)


# ─── CRUD ────────────────────────────────────────────────────────────────────

@router.get("/{tarea_id}", response_model=TareaResponse, response_model_exclude_none=True)
def obtener_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return tarea_service.obtener_tarea(db, tarea_id, studio_id)


@router.put("/{tarea_id}", response_model=TareaResponse, response_model_exclude_none=True)
def actualizar_tarea(
    tarea_id: int,
    data: TareaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return tarea_service.actualizar_tarea(db, tarea_id, data, studio_id)


@router.put("/{tarea_id}/asignar", response_model=TareaResponse, response_model_exclude_none=True)
def asignar_empleado(
    tarea_id: int,
    empleado_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return tarea_service.asignar_empleado(db, tarea_id, empleado_id, studio_id)


@router.patch("/{tarea_id}/prioridad", response_model=TareaResponse)
def patch_prioridad_eisenhower(
    tarea_id: int,
    data: PrioridadEisenhowerUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL_TAREA),
    studio_id: int = Depends(get_studio_id),
):
    """Actualiza es_urgente y es_importante de una tarea."""
    return tarea_service.patch_prioridad_eisenhower(
        db, tarea_id, studio_id, data.es_urgente, data.es_importante
    )


@router.delete("/{tarea_id}", status_code=204)
def eliminar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    tarea_service.eliminar_tarea(db, tarea_id, studio_id)


# ─── Tracking de tiempo ───────────────────────────────────────────────────────

@router.post("/{tarea_id}/iniciar", response_model=TareaResponse)
def iniciar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Abre una sesión de trabajo y cambia el estado a en_progreso."""
    empleado_id = current_user.get("empleado_id")
    return tarea_service.iniciar_tarea(db, tarea_id, empleado_id, studio_id)


@router.post("/{tarea_id}/pausar", response_model=TareaResponse)
def pausar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Cierra la sesión activa y vuelve el estado a pendiente."""
    return tarea_service.pausar_tarea(db, tarea_id, studio_id)


@router.post("/{tarea_id}/completar", response_model=TareaResponse)
def completar_tarea(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Cierra la sesión activa si existe y marca la tarea como completada."""
    return tarea_service.completar_tarea(db, tarea_id, studio_id)


@router.get("/{tarea_id}/tiempo")
def obtener_tiempo(
    tarea_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Retorna tiempo estimado, tiempo real acumulado y lista de sesiones."""
    return tarea_service.obtener_tiempo_tarea(db, tarea_id, studio_id)
