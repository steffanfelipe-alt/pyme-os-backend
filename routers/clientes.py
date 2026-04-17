from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import filtrar_clientes_por_rol, get_studio_id, require_rol, solo_dueno, verificar_acceso_cliente
from database import get_db
from models.cliente import Cliente, TipoCliente, TipoPersona
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
    studio_id: int = Depends(get_studio_id),
):
    return cliente_service.crear_cliente(db, data, studio_id)


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
    studio_id: int = Depends(get_studio_id),
):
    # Contador solo ve sus clientes asignados
    if current_user.get("rol") == "contador":
        contador_asignado_id = current_user.get("empleado_id")
    return cliente_service.listar_clientes(
        db, studio_id, skip, limit, tipo_persona, activo, busqueda, contador_asignado_id, estado_alerta
    )


@router.get("/{cliente_id}/ficha", response_model=FichaClienteResponse)
def obtener_ficha_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    verificar_acceso_cliente(current_user, cliente_id, db)
    return cliente_service.obtener_ficha_cliente(db, cliente_id, studio_id)


@router.get("/{cliente_id}", response_model=ClienteResponse, response_model_exclude_none=True)
def obtener_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    verificar_acceso_cliente(current_user, cliente_id, db)
    return cliente_service.obtener_cliente(db, cliente_id, studio_id)


@router.put("/{cliente_id}", response_model=ClienteResponse, response_model_exclude_none=True)
def actualizar_cliente(
    cliente_id: int,
    data: ClienteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return cliente_service.actualizar_cliente(db, cliente_id, data, studio_id)


@router.delete("/{cliente_id}", status_code=204)
def eliminar_cliente(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    cliente_service.eliminar_cliente(db, cliente_id, studio_id)


@router.post("/{cliente_id}/aplicar-plantillas")
def aplicar_plantillas(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return plantilla_service.aplicar_plantillas_a_cliente(db, cliente_id, studio_id)


@router.get("/por-tipo/{tipo}", response_model=list[ClienteResponse])
def listar_clientes_por_tipo(
    tipo: TipoCliente,
    page: int = 1,
    size: int = 20,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Lista clientes filtrados por tipo_cliente. Devuelve lista vacía si no hay resultados."""
    skip = (page - 1) * size
    clientes = (
        db.query(Cliente)
        .filter(Cliente.studio_id == studio_id, Cliente.tipo_cliente == tipo, Cliente.activo == True)
        .offset(skip)
        .limit(size)
        .all()
    )
    return clientes


@router.post("/importar", status_code=201)
async def importar_clientes_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return await cliente_service.importar_desde_csv(db, file, studio_id)


class NotasUpdate(BaseModel):
    notas: str | None = None


@router.patch("/{cliente_id}/notas")
def actualizar_notas(
    cliente_id: int,
    data: NotasUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """Actualiza las notas internas del contador para un cliente."""
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.studio_id == studio_id
    ).first()
    if not cliente:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    cliente.notas = data.notas
    db.commit()
    return {"ok": True, "notas": cliente.notas}
