from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from auth import get_current_user
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
    current_user: dict = Depends(get_current_user),
):
    return await documento_service.subir_documento(db, cliente_id, file, vencimiento_id)


@router.get(
    "/api/clientes/{cliente_id}/documentos",
    response_model=list[DocumentoResponse],
)
def listar_documentos(
    cliente_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return documento_service.listar_documentos(db, cliente_id)


@router.put(
    "/api/documentos/{doc_id}",
    response_model=DocumentoResponse,
)
def actualizar_documento(
    doc_id: int,
    data: DocumentoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return documento_service.actualizar_documento(db, doc_id, data)


@router.get(
    "/api/clientes/{cliente_id}/documentos/checklist",
    response_model=ChecklistResponse,
)
def checklist_documentacion(
    cliente_id: int,
    periodo: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Retorna el estado de documentación de un cliente para un período fiscal.
    Indica qué documentos llegaron, cuáles faltan, y el % de completitud.
    """
    return documento_service.obtener_checklist(db, cliente_id, periodo)


@router.delete(
    "/api/documentos/{doc_id}",
    status_code=204,
)
def eliminar_documento(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    documento_service.eliminar_documento(db, doc_id)
