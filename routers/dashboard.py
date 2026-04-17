from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol
from database import get_db
from schemas.dashboard import DashboardResponse
from services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("", response_model=DashboardResponse)
def obtener_dashboard(
    contador_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
    studio_id: int = Depends(get_studio_id),
):
    return dashboard_service.obtener_dashboard(db, contador_id, studio_id)
