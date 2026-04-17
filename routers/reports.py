from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, solo_dueno
from database import get_db
from services import report_service

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class GenerarInformeRequest(BaseModel):
    periodo: str


@router.post("/generate", status_code=201)
def generar_informe(
    body: GenerarInformeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Genera y persiste el informe ejecutivo mensual. ai_interpretation se completa en background."""
    informe = report_service.generar_informe(db, body.periodo, generado_por_id=current_user.get("id"), studio_id=studio_id)
    background_tasks.add_task(report_service.generar_interpretacion_background, informe["id"])
    return informe


@router.get("/")
def listar_informes(
    periodo: str | None = Query(default=None, description="Filtrar por período YYYY-MM"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Lista todos los informes ejecutivos, opcionalmente filtrados por período."""
    return report_service.listar_informes(db, periodo)


@router.get("/{informe_id}")
def obtener_informe(
    informe_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Retorna un informe ejecutivo por su ID."""
    return report_service.obtener_informe(db, informe_id)
