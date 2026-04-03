from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from auth_dependencies import filtrar_clientes_por_rol, require_rol, solo_dueno, verificar_acceso_cliente
from database import get_db
from models.cliente import Cliente, TipoPersona
from schemas.cliente import (
    ClienteCreate,
    ClienteResumen,
    ClienteResponse,
    ClienteUpdate,
    EstadoAlerta,
    FichaClienteResponse,
)
from services import cliente_service
from services import plantilla_service

router = APIRouter(prefix="/api/clientes", tags=["Clientes"])


@router.post("", response_model=ClienteResponse, status_code=201)
def crear_cliente(
    data: ClienteCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
):
    return cliente_service.crear_cliente(db, data)


@router.get("", response_model=list[ClienteResumen], response_model_exclude_none=True)
def listar_clientes(
    skip: int = 0,
    limit: int = 20,
    tipo_persona: Optional[TipoPersona] = None,
    activo: Optional[bool] = True,
    busqueda: Optional[str] = None,
    contador_asignado_id: Optional[int] = None,
    estado_alerta: Optional[EstadoAlerta] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    # Contador solo ve sus clientes asignados
    if current_user.get("rol") == "contador":
        contador_asignado_id = current_user.get("empleado_id")
    return cliente_service.listar_clientes(
        db, skip, limit, tipo_persona, activo, busqueda, contador_asignado_id, estado_alerta
    )


@router.get("/{cliente_id}/ficha", response_model=FichaClienteResponse)
def obtener_ficha_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    verificar_acceso_cliente(current_user, cliente_id, db)
    return cliente_service.obtener_ficha_cliente(db, cliente_id)


@router.get("/{cliente_id}", response_model=ClienteResponse, response_model_exclude_none=True)
def obtener_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    verificar_acceso_cliente(current_user, cliente_id, db)
    return cliente_service.obtener_cliente(db, cliente_id)


@router.put("/{cliente_id}", response_model=ClienteResponse, response_model_exclude_none=True)
def actualizar_cliente(
    cliente_id: int,
    data: ClienteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
):
    return cliente_service.actualizar_cliente(db, cliente_id, data)


@router.delete("/{cliente_id}", status_code=204)
def eliminar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    cliente_service.eliminar_cliente(db, cliente_id)


@router.post("/{cliente_id}/aplicar-plantillas")
def aplicar_plantillas(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
):
    return plantilla_service.aplicar_plantillas_a_cliente(db, cliente_id)


@router.post("/importar", status_code=201)
async def importar_clientes_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
):
    return await cliente_service.importar_desde_csv(db, file)
