from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models.cliente import CondicionFiscal
from schemas.plantilla_vencimiento import PlantillaCreate, PlantillaResponse, PlantillaUpdate
from services import plantilla_service

router = APIRouter(prefix="/api/plantillas", tags=["Plantillas"])


@router.post("", response_model=PlantillaResponse, status_code=201)
def crear_plantilla(
    data: PlantillaCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return plantilla_service.crear_plantilla(db, data)


@router.get("", response_model=list[PlantillaResponse])
def listar_plantillas(
    condicion_fiscal: Optional[CondicionFiscal] = None,
    activo: Optional[bool] = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return plantilla_service.listar_plantillas(db, condicion_fiscal, activo)


@router.get("/{plantilla_id}", response_model=PlantillaResponse)
def obtener_plantilla(
    plantilla_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return plantilla_service.obtener_plantilla(db, plantilla_id)


@router.put("/{plantilla_id}", response_model=PlantillaResponse)
def actualizar_plantilla(
    plantilla_id: int,
    data: PlantillaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return plantilla_service.actualizar_plantilla(db, plantilla_id, data)


@router.delete("/{plantilla_id}", status_code=204)
def eliminar_plantilla(
    plantilla_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    plantilla_service.eliminar_plantilla(db, plantilla_id)
