import calendar
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.informe_ejecutivo import InformeEjecutivo
from models.vencimiento import EstadoVencimiento, Vencimiento
from services import alert_service, profitability_service, risk_service, workload_service


def _parse_periodo(periodo: str) -> tuple[date, date]:
    """Devuelve (primer_dia, ultimo_dia) del mes YYYY-MM."""
    if len(periodo) != 7 or periodo[4] != "-":
        raise HTTPException(status_code=400, detail="Formato de período inválido. Usar YYYY-MM.")
    try:
        anio, mes = int(periodo[:4]), int(periodo[5:7])
        if mes < 1 or mes > 12:
            raise ValueError()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de período inválido. Usar YYYY-MM.")
    primer_dia = date(anio, mes, 1)
    ultimo_dia = date(anio, mes, calendar.monthrange(anio, mes)[1])
    return primer_dia, ultimo_dia


def _informe_a_dict(informe: InformeEjecutivo) -> dict:
    return {
        "id": informe.id,
        "periodo": informe.periodo,
        "generado_por_id": informe.generado_por_id,
        "total_clientes_activos": informe.total_clientes_activos,
        "alertas_criticas": informe.alertas_criticas,
        "clientes_riesgo_rojo": informe.clientes_riesgo_rojo,
        "resumen_vencimientos": informe.resumen_vencimientos,
        "resumen_workload": informe.resumen_workload,
        "resumen_rentabilidad": informe.resumen_rentabilidad,
        "resumen_alertas": informe.resumen_alertas,
        "resumen_riesgo": informe.resumen_riesgo,
        "created_at": informe.created_at.isoformat() if informe.created_at else None,
    }


def generar_informe(db: Session, periodo: str, generado_por_id: int | None = None) -> dict:
    """
    Consolida datos del período en un InformeEjecutivo y lo persiste.
    Si ya existe un informe para ese período, lo sobreescribe.
    """
    primer_dia, ultimo_dia = _parse_periodo(periodo)

    # --- Vencimientos del período ---
    vencimientos = db.query(Vencimiento).filter(
        Vencimiento.fecha_vencimiento >= primer_dia,
        Vencimiento.fecha_vencimiento <= ultimo_dia,
    ).all()
    conteo_estados = {}
    for v in vencimientos:
        estado = v.estado.value if hasattr(v.estado, "value") else str(v.estado)
        conteo_estados[estado] = conteo_estados.get(estado, 0) + 1
    resumen_vencimientos = {
        "total": len(vencimientos),
        "por_estado": conteo_estados,
    }

    # --- Workload ---
    resumen_workload = workload_service.obtener_resumen_carga(db)

    # --- Rentabilidad del período ---
    snapshots = profitability_service.listar_rentabilidad(db, periodo)
    horas_totales = sum(s["horas_reales"] for s in snapshots)
    con_rentabilidad = [s for s in snapshots if s["rentabilidad_hora"] is not None]
    avg_rentabilidad = (
        round(sum(s["rentabilidad_hora"] for s in con_rentabilidad) / len(con_rentabilidad), 2)
        if con_rentabilidad else None
    )
    resumen_rentabilidad = {
        "total_clientes_con_snapshot": len(snapshots),
        "horas_totales": round(horas_totales, 2),
        "avg_rentabilidad_hora": avg_rentabilidad,
        "clientes_sin_honorario": sum(1 for s in snapshots if not s["honorario_configurado"]),
    }

    # --- Alertas ---
    resumen_alertas = alert_service.resumen_alertas(db)

    # --- Riesgo ---
    clientes_riesgo = risk_service.listar_clientes_por_riesgo(db)
    conteo_riesgo = {"verde": 0, "amarillo": 0, "rojo": 0, "sin_calcular": 0}
    for c in clientes_riesgo:
        nivel = c["risk_level"] or "sin_calcular"
        if nivel in conteo_riesgo:
            conteo_riesgo[nivel] += 1
        else:
            conteo_riesgo["sin_calcular"] += 1
    resumen_riesgo = conteo_riesgo

    # --- Totales desnormalizados ---
    total_clientes_activos = db.query(Cliente).filter(Cliente.activo == True).count()
    alertas_criticas = resumen_alertas.get("criticas", 0)
    clientes_riesgo_rojo = conteo_riesgo["rojo"]

    # Sobreescribir si ya existe para el mismo período
    informe = db.query(InformeEjecutivo).filter(
        InformeEjecutivo.periodo == periodo,
    ).first()

    if informe:
        informe.generado_por_id = generado_por_id
        informe.resumen_vencimientos = resumen_vencimientos
        informe.resumen_workload = resumen_workload
        informe.resumen_rentabilidad = resumen_rentabilidad
        informe.resumen_alertas = resumen_alertas
        informe.resumen_riesgo = resumen_riesgo
        informe.total_clientes_activos = total_clientes_activos
        informe.alertas_criticas = alertas_criticas
        informe.clientes_riesgo_rojo = clientes_riesgo_rojo
    else:
        informe = InformeEjecutivo(
            periodo=periodo,
            generado_por_id=generado_por_id,
            resumen_vencimientos=resumen_vencimientos,
            resumen_workload=resumen_workload,
            resumen_rentabilidad=resumen_rentabilidad,
            resumen_alertas=resumen_alertas,
            resumen_riesgo=resumen_riesgo,
            total_clientes_activos=total_clientes_activos,
            alertas_criticas=alertas_criticas,
            clientes_riesgo_rojo=clientes_riesgo_rojo,
        )
        db.add(informe)

    db.commit()
    db.refresh(informe)
    return _informe_a_dict(informe)


def obtener_informe(db: Session, informe_id: int) -> dict:
    informe = db.query(InformeEjecutivo).filter(InformeEjecutivo.id == informe_id).first()
    if not informe:
        raise HTTPException(status_code=404, detail="Informe no encontrado")
    return _informe_a_dict(informe)


def listar_informes(db: Session, periodo: str | None = None) -> list[dict]:
    query = db.query(InformeEjecutivo)
    if periodo:
        query = query.filter(InformeEjecutivo.periodo == periodo)
    informes = query.order_by(InformeEjecutivo.created_at.desc()).all()
    return [_informe_a_dict(i) for i in informes]
