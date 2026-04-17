from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol, solo_dueno, verificar_acceso_cliente
from database import get_db
from schemas.documento import ChecklistResponse, DocumentoResponse, DocumentoUpdate
from services import documento_service

router = APIRouter(tags=["Documentos"])


@router.post(
    "/api/clientes/{cliente_id}/documentos",
    response_model=DocumentoResponse,
    status_code=201,
)
async def subir_documento(
    cliente_id: int,
    file: UploadFile = File(...),
    vencimiento_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    verificar_acceso_cliente(current_user, cliente_id, db)
    return await documento_service.subir_documento(db, cliente_id, file, studio_id, vencimiento_id)


@router.get(
    "/api/clientes/{cliente_id}/documentos",
    response_model=list[DocumentoResponse],
)
def listar_documentos(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    verificar_acceso_cliente(current_user, cliente_id, db)
    return documento_service.listar_documentos(db, cliente_id, studio_id)


@router.put(
    "/api/documentos/{doc_id}",
    response_model=DocumentoResponse,
)
def actualizar_documento(
    doc_id: int,
    data: DocumentoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return documento_service.actualizar_documento(db, doc_id, data, studio_id)


@router.get(
    "/api/clientes/{cliente_id}/documentos/checklist",
    response_model=ChecklistResponse,
)
def checklist_documentacion(
    cliente_id: int,
    periodo: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    """
    Retorna el estado de documentación de un cliente para un período fiscal.
    Indica qué documentos llegaron, cuáles faltan, y el % de completitud.
    """
    verificar_acceso_cliente(current_user, cliente_id, db)
    return documento_service.obtener_checklist(db, cliente_id, periodo, studio_id)


@router.delete(
    "/api/documentos/{doc_id}",
    status_code=204,
)
def eliminar_documento(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    documento_service.eliminar_documento(db, doc_id, studio_id)
