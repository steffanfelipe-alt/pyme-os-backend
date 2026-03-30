import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.documento import Documento, EstadoDocumento
from models.empleado import Empleado
from models.tarea import EstadoTarea, Tarea, TipoTarea
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
    TareaRetrasada,
    TasaAlertas,
    TiempoPromedioTipo,
    TiempoRealCliente,
    VencimientoSinDoc,
)

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


def obtener_dashboard(db: Session, contador_id: Optional[int] = None) -> DashboardResponse:
    hoy = date.today()
    ahora = datetime.now()

    # ── filtro base de clientes ──────────────────────────────────────────
    filtro_clientes = [Cliente.activo == True]
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
        .join(Cliente, Tarea.cliente_id == Cliente.id)
        .outerjoin(Empleado, Tarea.empleado_id == Empleado.id)
        .filter(
            Tarea.cliente_id.in_(clientes_ids_sq),
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
            cliente_nombre=c.nombre,
            contador_nombre=e.nombre if e else None,
            dias_retraso=(hoy - t.fecha_limite).days,
        )
        for t, c, e in tareas_ret_rows
    ]

    # 4. Tasa de alertas
    semana_inicio = hoy - timedelta(days=7)
    semana_ant_inicio = hoy - timedelta(days=14)
    semana_ant_fin = hoy - timedelta(days=7)

    def _contar_alertas(fecha_desde: date, fecha_hasta: date) -> int:
        venc_count = db.query(func.count(Vencimiento.id)).filter(
            Vencimiento.cliente_id.in_(clientes_ids_sq),
            Vencimiento.estado == EstadoVencimiento.vencido,
            Vencimiento.fecha_vencimiento >= fecha_desde,
            Vencimiento.fecha_vencimiento <= fecha_hasta,
        ).scalar() or 0
        tarea_count = db.query(func.count(Tarea.id)).filter(
            Tarea.cliente_id.in_(clientes_ids_sq),
            Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
            Tarea.fecha_limite >= fecha_desde,
            Tarea.fecha_limite <= fecha_hasta,
            Tarea.activo == True,
        ).scalar() or 0
        return venc_count + tarea_count

    alertas_semana = _contar_alertas(semana_inicio, hoy)
    alertas_ant = _contar_alertas(semana_ant_inicio, semana_ant_fin)
    if alertas_semana > alertas_ant:
        tendencia = "sube"
    elif alertas_semana < alertas_ant:
        tendencia = "baja"
    else:
        tendencia = "igual"

    bloque_riesgo = BloqueRiesgo(
        vencimientos_sin_docs=vencimientos_sin_docs,
        clientes_sin_actividad=clientes_sin_actividad,
        tareas_retrasadas=tareas_retrasadas,
        tasa_alertas=TasaAlertas(
            esta_semana=alertas_semana,
            semana_anterior=alertas_ant,
            tendencia=tendencia,
        ),
    )

    # ══════════════════════════════════════════════════════════════════════
    # BLOQUE CARGA
    # ══════════════════════════════════════════════════════════════════════

    empleados = db.query(Empleado).filter(Empleado.activo == True).all()
    if contador_id is not None:
        empleados = [e for e in empleados if e.id == contador_id]

    carga_por_contador = []
    total_tareas_activas = 0
    for emp in empleados:
        pend = db.query(func.count(Tarea.id)).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.pendiente,
            Tarea.activo == True,
            Tarea.cliente_id.in_(clientes_ids_sq),
        ).scalar() or 0
        en_prog = db.query(func.count(Tarea.id)).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.en_progreso,
            Tarea.activo == True,
            Tarea.cliente_id.in_(clientes_ids_sq),
        ).scalar() or 0
        horas_est = db.query(func.coalesce(func.sum(Tarea.tiempo_estimado), 0)).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
            Tarea.activo == True,
            Tarea.cliente_id.in_(clientes_ids_sq),
        ).scalar() or 0
        horas_est_f = round(horas_est / 60, 1)
        pct = round(horas_est_f / emp.capacidad_horas_mes * 100, 1) if emp.capacidad_horas_mes else 0
        total_tareas_activas += pend + en_prog
        carga_por_contador.append(CargaContador(
            empleado_id=emp.id,
            nombre=emp.nombre,
            rol=emp.rol.value,
            tareas_pendientes=pend,
            tareas_en_progreso=en_prog,
            horas_estimadas=horas_est_f,
            capacidad_horas_mes=emp.capacidad_horas_mes,
            porcentaje_carga=pct,
            color=_color_carga(pct),
        ))

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
            func.avg(Tarea.tiempo_real).label("promedio"),
            func.count(Tarea.id).label("cantidad"),
        )
        .filter(
            Tarea.estado == EstadoTarea.completada,
            Tarea.tiempo_real.isnot(None),
            Tarea.activo == True,
            Tarea.cliente_id.in_(clientes_ids_sq),
        )
        .group_by(Tarea.tipo)
        .all()
    )
    tiempo_promedio = [
        TiempoPromedioTipo(
            tipo=row.tipo.value,
            promedio_minutos=round(row.promedio or 0, 1),
            cantidad=row.cantidad,
        )
        for row in tipo_stats
    ]

    # Índice de concentración
    if total_tareas_activas > 0 and carga_por_contador:
        max_tareas = max(c.tareas_pendientes + c.tareas_en_progreso for c in carga_por_contador)
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

    # Tiempo real invertido x cliente — mes actual
    tiempo_real_rows = (
        db.query(
            Tarea.cliente_id,
            Cliente.nombre,
            func.coalesce(func.sum(Tarea.tiempo_real), 0).label("total_min"),
        )
        .join(Cliente, Tarea.cliente_id == Cliente.id)
        .filter(
            Tarea.cliente_id.in_(clientes_ids_sq),
            Tarea.estado == EstadoTarea.completada,
            Tarea.fecha_completada >= mes_inicio,
            Tarea.tiempo_real.isnot(None),
            Tarea.activo == True,
        )
        .group_by(Tarea.cliente_id, Cliente.nombre)
        .order_by(func.sum(Tarea.tiempo_real).desc())
        .all()
    )
    tiempo_real_por_cliente = [
        TiempoRealCliente(
            cliente_id=r.cliente_id,
            nombre=r.nombre,
            horas_mes=round(r.total_min / 60, 1),
        )
        for r in tiempo_real_rows
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
            func.date_trunc('month', Cliente.created_at) == func.date_trunc('month', mes_ref_inicio)
        ).scalar() or 0
        bajas = db.query(func.count(Cliente.id)).filter(
            Cliente.fecha_baja.isnot(None),
            func.date_trunc('month', Cliente.fecha_baja) == func.date_trunc('month', mes_ref_inicio)
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

    # Rentabilidad x cliente
    rentabilidad_rows = (
        db.query(
            Cliente.id,
            Cliente.nombre,
            Cliente.honorarios_mensuales,
            func.coalesce(func.sum(Tarea.tiempo_real), 0).label("min_mes"),
        )
        .outerjoin(
            Tarea,
            and_(
                Tarea.cliente_id == Cliente.id,
                Tarea.estado == EstadoTarea.completada,
                Tarea.fecha_completada >= mes_inicio,
                Tarea.activo == True,
            ),
        )
        .filter(Cliente.id.in_(clientes_ids_sq))
        .group_by(Cliente.id, Cliente.nombre, Cliente.honorarios_mensuales)
        .all()
    )

    rentabilidad_por_cliente = []
    for r in rentabilidad_rows:
        horas = round(r.min_mes / 60, 1) if r.min_mes else 0.0
        honorarios = float(r.honorarios_mensuales) if r.honorarios_mensuales else None
        if honorarios is None or horas == 0:
            semaforo = "sin_datos"
            costo_hora = None
        else:
            costo_hora = round(honorarios / horas, 0)
            if costo_hora >= COSTO_HORA_RENTABLE:
                semaforo = "rentable"
            elif costo_hora >= COSTO_HORA_NEUTRO:
                semaforo = "neutro"
            else:
                semaforo = "deficitario"
        rentabilidad_por_cliente.append(RentabilidadCliente(
            cliente_id=r.id,
            nombre=r.nombre,
            honorarios=honorarios,
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
