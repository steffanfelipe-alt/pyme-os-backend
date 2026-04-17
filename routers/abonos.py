"""F1 + F2 — Abonos y cobros."""
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, require_rol, solo_dueno
from database import get_db
from models.abono import EstadoCobro
from schemas.abono import AbonoCreate, AbonoResponse, AbonoUpdate, CobroResponse
from services import abono_service

router = APIRouter(prefix="/api/abonos", tags=["Abonos"])

_ROL = require_rol("dueno", "contador", "administrativo")


# ── Rutas estáticas (antes de rutas con parámetros) ───────────────────────────

@router.get("/cobros/pendientes", response_model=list[CobroResponse])
def cobros_pendientes(
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    cobros = abono_service.listar_cobros(db, studio_id, estado=EstadoCobro.pendiente)
    return cobros


@router.get("/cobros/vencidos", response_model=list[CobroResponse])
def cobros_vencidos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    cobros = abono_service.listar_cobros(db, studio_id, estado=EstadoCobro.vencido)
    return cobros


@router.post("/cobros/evaluar-vencidos", status_code=200)
def evaluar_vencidos(
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    """F2 — Marca como vencidos los cobros pendientes cuya fecha ya pasó."""
    resultado = abono_service.evaluar_cobros_vencidos(db, studio_id)
    return {"marcados_vencidos": len(resultado), "cobros": resultado}


@router.get("/cobros/resumen")
def resumen_cobros(
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    return abono_service.resumen_cobros(db, studio_id)


# ── Abonos CRUD ───────────────────────────────────────────────────────────────

@router.post("", response_model=AbonoResponse, status_code=201)
def crear_abono(
    data: AbonoCreate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    return abono_service.crear_abono(db, studio_id, data.model_dump())


@router.get("", response_model=list[AbonoResponse])
def listar_abonos(
    cliente_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    return abono_service.listar_abonos(db, studio_id, cliente_id)


@router.get("/{abono_id}", response_model=AbonoResponse)
def obtener_abono(
    abono_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    return abono_service.obtener_abono(db, abono_id, studio_id)


@router.put("/{abono_id}", response_model=AbonoResponse)
def actualizar_abono(
    abono_id: int,
    data: AbonoUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    return abono_service.actualizar_abono(db, abono_id, studio_id, data.model_dump(exclude_none=True))


@router.delete("/{abono_id}", status_code=204)
def eliminar_abono(
    abono_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    abono_service.eliminar_abono(db, abono_id, studio_id)


# ── Cobros por abono ──────────────────────────────────────────────────────────

@router.get("/{abono_id}/cobros", response_model=list[CobroResponse])
def listar_cobros_abono(
    abono_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    return abono_service.listar_cobros(db, studio_id, abono_id=abono_id)


@router.patch("/{abono_id}/cobros/{cobro_id}/pagar", response_model=CobroResponse)
def registrar_pago(
    abono_id: int,
    cobro_id: int,
    notas: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(_ROL),
    studio_id: int = Depends(get_studio_id),
):
    return abono_service.registrar_cobro_pagado(db, cobro_id, studio_id, notas)
