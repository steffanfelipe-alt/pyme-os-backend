import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.documento import Documento, EstadoDocumento
from models.empleado import Empleado
from models.tarea import EstadoTarea, Tarea
from models.vencimiento import EstadoVencimiento, Vencimiento
from schemas.dashboard import (
    BloqueRiesgo,
    BloqueCarga,
    BloqueSalud,
    CargaContador,
    ClienteSinActividad,
    CompletadasATiempo,
    DashboardResponse,
    DocumentacionCliente,
    EvolucionMensual,
    IndiceConcentracion,
    RentabilidadCliente,
    ResumenAlertas,
    TareaRetrasada,
    TiempoPromedioTipo,
    TiempoRealCliente,
    VencimientoSinDoc,
)
from services import alert_service, profitability_service

logger = logging.getLogger("pymeos")

UMBRAL_SIN_ACTIVIDAD_DIAS = 30
COSTO_HORA_RENTABLE = 1500.0
COSTO_HORA_NEUTRO = 800.0


def _urgencia(dias: int) -> str:
    if dias < 3:
        return "CRITICO"
    if dias < 7:
        return "URGENTE"
    return "PROXIMO"


def _color_carga(pct: float) -> str:
    if pct < 70:
        return "verde"
    if pct <= 90:
        return "amarillo"
    return "rojo"


def obtener_dashboard(db: Session, contador_id: Optional[int] = None, studio_id: Optional[int] = None) -> DashboardResponse:  # noqa: C901
    hoy = date.today()
    ahora = datetime.now()
    try:
        return _calcular_dashboard(db, contador_id, hoy, ahora, studio_id)
    except Exception as exc:
        logger.error("Error generando dashboard: %s", exc, exc_info=True)
        return DashboardResponse(
            bloque_riesgo=BloqueRiesgo(
                vencimientos_sin_docs=[],
                clientes_sin_actividad=[],
                tareas_retrasadas=[],
                alertas_activas=ResumenAlertas(criticas=0, advertencias=0, informativas=0),
            ),
            bloque_carga=BloqueCarga(
                carga_por_contador=[],
                completadas_a_tiempo=CompletadasATiempo(total_pct=0.0, mes_anterior_pct=None),
                tiempo_promedio_resolucion=[],
                indice_concentracion=IndiceConcentracion(alerta=False, top_contador_pct=0.0, mensaje=None),
            ),
            bloque_salud=BloqueSalud(
                tiempo_real_por_cliente=[],
                documentacion_por_cliente=[],
                evolucion_clientes=[],
                rentabilidad_por_cliente=[],
            ),
            generado_en=ahora,
            filtrado_por_contador=contador_id,
            error="Error al calcular métricas. Verificá los datos de la base.",
        )


def _calcular_dashboard(db: Session, contador_id: Optional[int], hoy: date, ahora: datetime, studio_id: Optional[int] = None) -> DashboardResponse:

    # ── filtro base de clientes ───────────────────────────────────────────────────────────────────────────────────
    filtro_clientes = [Cliente.activo == True]
    if studio_id is not None:
        filtro_clientes.append(Cliente.studio_id == studio_id)
    if contador_id is not None:
        filtro_clientes.append(Cliente.contador_asignado_id == contador_id)

    clientes_ids_sq = (
        select(Cliente.id)
        .where(and_(*filtro_clientes))
        .scalar_subquery()
    )

    # ══════════════════════════════════════════════════════════════════════
    # BLOQUE RIESGO
    # ══════════════════════════════════════════════════════════════════════

    # 1. Vencimientos próximos sin documentación procesada
    limite_30 = hoy + timedelta(days=30)
    docs_procesados_sq = (
        select(Documento.vencimiento_id)
        .where(
            Documento.estado == EstadoDocumento.procesado,
            Documento.vencimiento_id.isnot(None),
            Documento.activo == True,
        )
        .scalar_subquery()
    )

    vencs_sin_doc_rows = (
        db.query(Vencimiento, Cliente, Empleado)
        .join(Cliente, Vencimiento.cliente_id == Cliente.id)
        .outerjoin(Empleado, Cliente.contador_asignado_id == Empleado.id)
        .filter(
            Vencimiento.cliente_id.in_(clientes_ids_sq),
            Vencimiento.estado == EstadoVencimiento.pendiente,
            Vencimiento.fecha_vencimiento <= limite_30,
            Vencimiento.id.notin_(docs_procesados_sq),
        )
        .order_by(Vencimiento.fecha_vencimiento)
        .all()
    )

    vencimientos_sin_docs = [
        VencimientoSinDoc(
            cliente_id=v.cliente_id,
            cliente_nombre=c.nombre,
            tipo=v.tipo,
            fecha_vencimiento=v.fecha_vencimiento,
            dias_restantes=(v.fecha_vencimiento - hoy).days,
            urgencia=_urgencia((v.fecha_vencimiento - hoy).days),
            contador_nombre=e.nombre if e else None,
        )
        for v, c, e in vencs_sin_doc_rows
    ]

    # 2. Clientes sin actividad > 30 días
    sq_ult_tarea = (
        select(Tarea.cliente_id, func.max(Tarea.updated_at).label("ult"))
        .where(Tarea.activo == True)
        .group_by(Tarea.cliente_id)
        .subquery()
    )
    sq_ult_venc = (
        select(Vencimiento.cliente_id, func.max(Vencimiento.updated_at).label("ult"))
        .group_by(Vencimiento.cliente_id)
        .subquery()
    )

    sin_actividad_rows = (
        db.query(Cliente, Empleado,
                 func.greatest(sq_ult_tarea.c.ult, sq_ult_venc.c.ult).label("ultima"))
        .outerjoin(Empleado, Cliente.contador_asignado_id == Empleado.id)
        .outerjoin(sq_ult_tarea, Cliente.id == sq_ult_tarea.c.cliente_id)
        .outerjoin(sq_ult_venc, Cliente.id == sq_ult_venc.c.cliente_id)
        .filter(Cliente.id.in_(clientes_ids_sq))
        .all()
    )

    umbral_inactividad = ahora - timedelta(days=UMBRAL_SIN_ACTIVIDAD_DIAS)
    clientes_sin_actividad = []
    for c, e, ultima in sin_actividad_rows:
        if ultima is None or ultima < umbral_inactividad:
            dias = (ahora - ultima).days if ultima else 9999
            clientes_sin_actividad.append(ClienteSinActividad(
                cliente_id=c.id,
                nombre=c.nombre,
                ultima_actividad=ultima,
                dias_inactivo=dias,
                contador_nombre=e.nombre if e else None,
            ))

    # 3. Tareas retrasadas
    tareas_ret_rows = (
        db.query(Tarea, Cliente, Empleado)
        .outerjoin(Cliente, Tarea.cliente_id == Cliente.id)
        .outerjoin(Empleado, Tarea.empleado_id == Empleado.id)
        .filter(
            Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
            Tarea.fecha_limite < hoy,
            Tarea.activo == True,
        )
        .order_by(Tarea.fecha_limite)
        .all()
    )

    tareas_retrasadas = [
        TareaRetrasada(
            tarea_id=t.id,
            titulo=t.titulo,
            cliente_nombre=c.nombre if c else "Sin cliente",
            contador_nombre=e.nombre if e else None,
            dias_retraso=(hoy - t.fecha_limite).days,
        )
        for t, c, e in tareas_ret_rows
    ]

    # 4. Alertas activas — via alert_service
    resumen = alert_service.resumen_alertas(db, studio_id)

    bloque_riesgo = BloqueRiesgo(
        vencimientos_sin_docs=vencimientos_sin_docs,
        clientes_sin_actividad=clientes_sin_actividad,
        tareas_retrasadas=tareas_retrasadas,
        alertas_activas=ResumenAlertas(
            criticas=resumen["criticas"],
            advertencias=resumen["advertencias"],
            informativas=resumen["informativas"],
        ),
    )

    # ══════════════════════════════════════════════════════════════════════
    # BLOQUE CARGA
    # ══════════════════════════════════════════════════════════════════════

    emp_filtros = [Empleado.activo == True]
    if studio_id is not None:
        emp_filtros.append(Empleado.studio_id == studio_id)
    empleados_activos = db.query(Empleado).filter(*emp_filtros).all()
    emp_info = {e.id: e for e in empleados_activos}

    # Cálculo de carga inline (workload module eliminado en v2)
    def _calcular_panel_carga(empleados: list) -> list:
        panel = []
        for emp in empleados:
            tareas_activas = db.query(Tarea).filter(
                Tarea.empleado_id == emp.id,
                Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
                Tarea.activo == True,
            ).all()
            horas_comprometidas = sum(
                float(t.horas_estimadas or 0) for t in tareas_activas
            )
            horas_disponibles = float(emp.capacidad_horas_mes or 160)
            porcentaje_carga = round((horas_comprometidas / horas_disponibles) * 100, 1) if horas_disponibles > 0 else 0.0
            nivel = "alta" if porcentaje_carga >= 90 else ("media" if porcentaje_carga >= 60 else "baja")
            panel.append({
                "empleado_id": emp.id,
                "nombre": emp.nombre,
                "horas_comprometidas": round(horas_comprometidas, 1),
                "horas_disponibles": horas_disponibles,
                "porcentaje_carga": porcentaje_carga,
                "nivel": nivel,
                "cantidad_tareas": len(tareas_activas),
            })
        return panel

    panel = _calcular_panel_carga(empleados_activos)
    carga_por_contador = []
    for p in panel:
        if contador_id is not None and p["empleado_id"] != contador_id:
            continue
        emp = emp_info.get(p["empleado_id"])
        carga_por_contador.append(CargaContador(
            empleado_id=p["empleado_id"],
            nombre=p["nombre"],
            rol=emp.rol.value if emp else "",
            horas_comprometidas=p["horas_comprometidas"],
            horas_disponibles=p["horas_disponibles"],
            porcentaje_carga=p["porcentaje_carga"],
            nivel=p["nivel"],
            cantidad_tareas=p["cantidad_tareas"],
            color=_color_carga(p["porcentaje_carga"]),
        ))

    total_tareas_activas = sum(c.cantidad_tareas for c in carga_por_contador)

    # % completadas a tiempo — mes actual vs anterior
    mes_inicio = hoy.replace(day=1)
    mes_ant_inicio = (mes_inicio - timedelta(days=1)).replace(day=1)

    def _pct_a_tiempo(desde: date, hasta: date) -> float:
        total = db.query(func.count(Tarea.id)).filter(
            Tarea.estado == EstadoTarea.completada,
            Tarea.fecha_completada >= desde,
            Tarea.fecha_completada <= hasta,
            Tarea.activo == True,
            Tarea.cliente_id.in_(clientes_ids_sq),
        ).scalar() or 0
        if total == 0:
            return 0.0
        a_tiempo = db.query(func.count(Tarea.id)).filter(
            Tarea.estado == EstadoTarea.completada,
            Tarea.fecha_completada >= desde,
            Tarea.fecha_completada <= hasta,
            Tarea.fecha_completada <= Tarea.fecha_limite,
            Tarea.activo == True,
            Tarea.cliente_id.in_(clientes_ids_sq),
        ).scalar() or 0
        return round(a_tiempo / total * 100, 1)

    pct_actual = _pct_a_tiempo(mes_inicio, hoy)
    pct_anterior = _pct_a_tiempo(mes_ant_inicio, mes_inicio - timedelta(days=1))

    # Tiempo promedio de resolución por tipo de tarea
    tipo_stats = (
        db.query(
            Tarea.tipo,
            func.avg(Tarea.horas_reales).label("promedio"),
            func.count(Tarea.id).label("cantidad"),
        )
        .filter(
            Tarea.estado == EstadoTarea.completada,
            Tarea.horas_reales.isnot(None),
            Tarea.activo == True,
            Tarea.cliente_id.in_(clientes_ids_sq),
        )
        .group_by(Tarea.tipo)
        .all()
    )
    tiempo_promedio = [
        TiempoPromedioTipo(
            tipo=row.tipo.value,
            promedio_horas=round(row.promedio or 0, 1),
            cantidad=row.cantidad,
        )
        for row in tipo_stats
    ]

    # Índice de concentración
    if total_tareas_activas > 0 and carga_por_contador:
        max_tareas = max(c.cantidad_tareas for c in carga_por_contador)
        top_pct = round(max_tareas / total_tareas_activas * 100, 1)
        alerta_conc = top_pct >= 80
    else:
        top_pct = 0.0
        alerta_conc = False

    bloque_carga = BloqueCarga(
        carga_por_contador=carga_por_contador,
        completadas_a_tiempo=CompletadasATiempo(
            total_pct=pct_actual,
            mes_anterior_pct=pct_anterior,
        ),
        tiempo_promedio_resolucion=tiempo_promedio,
        indice_concentracion=IndiceConcentracion(
            alerta=alerta_conc,
            top_contador_pct=top_pct,
            mensaje="Concentración de carga riesgosa" if alerta_conc else None,
        ),
    )

    # ══════════════════════════════════════════════════════════════════════
    # BLOQUE SALUD
    # ══════════════════════════════════════════════════════════════════════

    # Horas reales invertidas x cliente — mes actual
    horas_reales_rows = (
        db.query(
            Tarea.cliente_id,
            Cliente.nombre,
            func.coalesce(func.sum(Tarea.horas_reales), 0.0).label("total_horas"),
        )
        .join(Cliente, Tarea.cliente_id == Cliente.id)
        .filter(
            Tarea.cliente_id.in_(clientes_ids_sq),
            Tarea.estado == EstadoTarea.completada,
            Tarea.fecha_completada >= mes_inicio,
            Tarea.horas_reales.isnot(None),
            Tarea.activo == True,
        )
        .group_by(Tarea.cliente_id, Cliente.nombre)
        .order_by(func.sum(Tarea.horas_reales).desc())
        .all()
    )
    tiempo_real_por_cliente = [
        TiempoRealCliente(
            cliente_id=r.cliente_id,
            nombre=r.nombre,
            horas_mes=round(r.total_horas, 1),
        )
        for r in horas_reales_rows
    ]

    # Documentación x cliente (% de vencimientos con doc procesada)
    docs_por_venc_sq = (
        select(Documento.vencimiento_id)
        .where(
            Documento.estado == EstadoDocumento.procesado,
            Documento.vencimiento_id.isnot(None),
            Documento.activo == True,
        )
        .subquery()
    )

    doc_stats_rows = (
        db.query(
            Vencimiento.cliente_id,
            Cliente.nombre,
            func.count(Vencimiento.id).label("total"),
            func.sum(
                case((Vencimiento.id.in_(select(docs_por_venc_sq.c.vencimiento_id)), 1), else_=0)
            ).label("con_doc"),
        )
        .join(Cliente, Vencimiento.cliente_id == Cliente.id)
        .filter(
            Vencimiento.cliente_id.in_(clientes_ids_sq),
            Vencimiento.estado.in_([EstadoVencimiento.pendiente, EstadoVencimiento.vencido]),
        )
        .group_by(Vencimiento.cliente_id, Cliente.nombre)
        .all()
    )
    documentacion_por_cliente = [
        DocumentacionCliente(
            cliente_id=r.cliente_id,
            nombre=r.nombre,
            vencimientos_total=r.total,
            con_documentacion=r.con_doc or 0,
            pct=round((r.con_doc or 0) / r.total * 100, 1) if r.total else 0,
        )
        for r in doc_stats_rows
    ]

    # Evolución mensual — últimos 6 meses
    evolucion = []
    for i in range(5, -1, -1):
        ref = (hoy.replace(day=1) - timedelta(days=1)) if i > 0 else hoy.replace(day=1)
        for _ in range(i):
            ref = (ref.replace(day=1) - timedelta(days=1))
        mes_ref_inicio = ref.replace(day=1)
        mes_ref_fin = (mes_ref_inicio.replace(month=mes_ref_inicio.month % 12 + 1, day=1)
                       if mes_ref_inicio.month < 12
                       else mes_ref_inicio.replace(year=mes_ref_inicio.year + 1, month=1, day=1))

        altas = db.query(func.count(Cliente.id)).filter(
            Cliente.created_at >= mes_ref_inicio,
            Cliente.created_at < mes_ref_fin,
        ).scalar() or 0
        bajas = db.query(func.count(Cliente.id)).filter(
            Cliente.fecha_baja.isnot(None),
            Cliente.fecha_baja >= mes_ref_inicio,
            Cliente.fecha_baja < mes_ref_fin,
        ).scalar() or 0
        activos = db.query(func.count(Cliente.id)).filter(
            Cliente.activo == True,
            Cliente.created_at < mes_ref_fin,
        ).scalar() or 0

        evolucion.append(EvolucionMensual(
            mes=mes_ref_inicio.strftime("%Y-%m"),
            activos=activos,
            altas=altas,
            bajas=bajas,
        ))

    # Rentabilidad x cliente — via profitability_service (snapshots del período actual)
    periodo_actual = hoy.strftime("%Y-%m")
    snapshots = profitability_service.listar_rentabilidad(db, periodo_actual, studio_id or 0)

    rentabilidad_por_cliente = []
    for s in snapshots:
        honorario = s["honorario"] if s["honorario_configurado"] else None
        horas = s["horas_reales"]
        costo_hora = s["rentabilidad_hora"]
        if costo_hora is None:
            semaforo = "sin_datos"
        elif costo_hora >= COSTO_HORA_RENTABLE:
            semaforo = "rentable"
        elif costo_hora >= COSTO_HORA_NEUTRO:
            semaforo = "neutro"
        else:
            semaforo = "deficitario"
        rentabilidad_por_cliente.append(RentabilidadCliente(
            cliente_id=s["cliente_id"],
            nombre=s["nombre"],
            honorarios=honorario,
            horas_mes=horas,
            costo_hora_estimado=costo_hora,
            semaforo=semaforo,
        ))

    bloque_salud = BloqueSalud(
        tiempo_real_por_cliente=tiempo_real_por_cliente,
        documentacion_por_cliente=documentacion_por_cliente,
        evolucion_clientes=evolucion,
        rentabilidad_por_cliente=rentabilidad_por_cliente,
    )

    logger.info("Dashboard generado — contador_id=%s", contador_id)
    return DashboardResponse(
        bloque_riesgo=bloque_riesgo,
        bloque_carga=bloque_carga,
        bloque_salud=bloque_salud,
        generado_en=ahora,
        filtrado_por_contador=contador_id,
    )
