import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from auth_dependencies import solo_dueno
from database import get_db
from models.vencimiento import EstadoVencimiento
from services import reportes_service

router = APIRouter(prefix="/api/reportes", tags=["Reportes"])


# ─── Studio Config ────────────────────────────────────────────────────────────

@router.get("/config")
def obtener_config(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Retorna la configuración del estudio (tarifa-hora, moneda, zona horaria)."""
    return reportes_service.obtener_config(db)


class ConfigUpdate(BaseModel):
    nombre_estudio: Optional[str] = None
    email_estudio: Optional[EmailStr] = None
    tarifa_hora_pesos: Optional[float] = None
    moneda: Optional[str] = None
    zona_horaria: Optional[str] = None


@router.put("/config")
def actualizar_config(
    data: ConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Actualiza configuración del estudio: nombre, email, tarifa-hora, moneda y/o zona horaria."""
    return reportes_service.actualizar_config(
        db,
        data.tarifa_hora_pesos,
        data.moneda,
        data.zona_horaria,
        data.nombre_estudio,
        data.email_estudio,
    )


class OptimizadorConfigUpdate(BaseModel):
    umbral_instancias: int


@router.patch("/config/optimizador")
def actualizar_config_optimizador(
    data: OptimizadorConfigUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Actualiza el umbral mínimo de instancias completadas para que el optimizador
    recalcule automáticamente los tiempos estimados. Rango válido: 1-50.
    """
    if not (1 <= data.umbral_instancias <= 50):
        raise HTTPException(status_code=422, detail="El umbral debe estar entre 1 y 50.")
    return reportes_service.actualizar_umbral_optimizador(db, data.umbral_instancias)


# ─── Reporte 1: Carga por empleado ───────────────────────────────────────────

@router.get("/carga")
def reporte_carga(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Carga de trabajo por empleado para el período YYYY-MM.
    Si no se envía período, usa el mes actual.
    """
    return reportes_service.reporte_carga(db, periodo)


# ─── Reporte 2: Rentabilidad por cliente ─────────────────────────────────────

@router.get("/rentabilidad")
def reporte_rentabilidad(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Rentabilidad por cliente usando horas reales de procesos + tarifa-hora configurada.
    Requiere tarifa-hora configurada en /reportes/config.
    """
    return reportes_service.reporte_rentabilidad(db, periodo)


# ─── Reporte 3: Vencimientos del período ─────────────────────────────────────

@router.get("/vencimientos")
def reporte_vencimientos(
    periodo: Optional[str] = None,
    estado: Optional[EstadoVencimiento] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Vencimientos del período con alertas para los que vencen en <= 7 días.
    Filtro opcional por estado.
    """
    return reportes_service.reporte_vencimientos(db, periodo, estado)


# ─── Reporte 4: Eficiencia de procesos ───────────────────────────────────────

@router.get("/procesos")
def reporte_procesos(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Eficiencia de procesos: desviación entre tiempo estimado y real.
    Solo incluye procesos con 5+ instancias completadas en el período.
    """
    return reportes_service.reporte_procesos(db, periodo)


# ─── Resumen ejecutivo ────────────────────────────────────────────────────────

@router.get("/resumen")
def reporte_resumen(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Resumen ejecutivo consolidado de los 4 reportes.
    Consume datos ya calculados — no recalcula todo de cero.
    """
    return reportes_service.reporte_resumen(db, periodo)


@router.get("/madurez")
def reporte_madurez(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Diagnóstico de madurez del estudio según las 4 etapas de SYSTEMology:
    Survival / Stationary / Scalable / Saleable.
    """
    return reportes_service.reporte_madurez(db)


# ─── Exports CSV ─────────────────────────────────────────────────────────────

@router.get("/vencimientos/export.csv")
def exportar_vencimientos_csv(
    periodo: Optional[str] = None,
    estado: Optional[EstadoVencimiento] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Descarga vencimientos del período como CSV."""
    data = reportes_service.reporte_vencimientos(db, periodo, estado)
    vencimientos = data.get("vencimientos", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["cliente", "tipo", "descripcion", "fecha_vencimiento", "estado", "dias_restantes", "alerta"])
    for v in vencimientos:
        writer.writerow([
            v.get("cliente_nombre"),
            v.get("tipo"),
            v.get("descripcion", ""),
            v.get("fecha_vencimiento"),
            v.get("estado"),
            v.get("dias_restantes", ""),
            v.get("alerta", False),
        ])

    output.seek(0)
    filename = f"vencimientos_{periodo or 'actual'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/rentabilidad/export.csv")
def exportar_rentabilidad_csv(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Descarga rentabilidad por cliente del período como CSV."""
    data = reportes_service.reporte_rentabilidad(db, periodo)
    clientes = data.get("clientes", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["cliente", "honorario_mensual", "horas_reales", "costo_estimado", "rentabilidad", "margen_pct", "alerta"])
    for c in clientes:
        writer.writerow([
            c.get("nombre"),
            c.get("honorario_mensual", ""),
            c.get("horas_reales", 0),
            c.get("costo_estimado", 0),
            c.get("rentabilidad", ""),
            c.get("margen_pct", ""),
            c.get("alerta", False),
        ])

    output.seek(0)
    filename = f"rentabilidad_{periodo or 'actual'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/carga/export.csv")
def exportar_carga_csv(
    periodo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Descarga carga de trabajo por empleado del período como CSV."""
    data = reportes_service.reporte_carga(db, periodo)
    empleados = data.get("empleados", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["empleado", "tareas_pendientes", "tareas_en_curso", "tareas_completadas_periodo", "nivel_carga"])
    for e in empleados:
        writer.writerow([
            e.get("nombre"),
            e.get("tareas_pendientes", 0),
            e.get("tareas_en_curso", 0),
            e.get("tareas_completadas_periodo", 0),
            e.get("nivel_carga", ""),
        ])

    output.seek(0)
    filename = f"carga_{periodo or 'actual'}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
