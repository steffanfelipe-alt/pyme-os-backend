"""
Módulo de Reportes — endpoints de consulta agregada que cruzan tablas existentes.
No genera nueva lógica de negocio; usa los datos ya registrados en el sistema.
"""
import calendar
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente, TipoCliente
from models.empleado import Empleado
from models.proceso import Automatizacion, EstadoRevisionAutomatizacion, ProcesoInstancia, ProcesoPasoInstancia, ProcesoPasoTemplate, ProcesoTemplate, EstadoInstancia
from models.sop_documento import EstadoSop, SopDocumento
from models.studio_config import StudioConfig
from models.tarea import EstadoTarea, Tarea
from models.tarea_sesion import TareaSesion
from models.vencimiento import EstadoVencimiento, Vencimiento


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _parse_periodo(periodo: Optional[str]) -> tuple[date, date, str]:
    """Retorna (primer_dia, ultimo_dia, periodo_str). Si periodo es None usa el mes actual."""
    if periodo is None:
        hoy = date.today()
        periodo = hoy.strftime("%Y-%m")

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
    return primer_dia, ultimo_dia, periodo


def _obtener_o_crear_config(db: Session) -> StudioConfig:
    """Retorna la config del estudio. Crea con valores por defecto si no existe."""
    config = db.query(StudioConfig).first()
    if not config:
        config = StudioConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


# ─── Studio Config ────────────────────────────────────────────────────────────

def obtener_config(db: Session) -> dict:
    config = _obtener_o_crear_config(db)
    return {
        "nombre_estudio": config.nombre_estudio,
        "email_estudio": config.email_estudio,
        "tarifa_hora_pesos": float(config.tarifa_hora_pesos) if config.tarifa_hora_pesos else None,
        "moneda": config.moneda,
        "zona_horaria": config.zona_horaria,
        "updated_at": config.updated_at.isoformat(),
    }


def actualizar_config(
    db: Session,
    tarifa_hora_pesos: Optional[float],
    moneda: Optional[str],
    zona_horaria: Optional[str],
    nombre_estudio: Optional[str] = None,
    email_estudio: Optional[str] = None,
) -> dict:
    config = _obtener_o_crear_config(db)
    if tarifa_hora_pesos is not None:
        config.tarifa_hora_pesos = Decimal(str(tarifa_hora_pesos))
    if moneda is not None:
        config.moneda = moneda
    if zona_horaria is not None:
        config.zona_horaria = zona_horaria
    if nombre_estudio is not None:
        config.nombre_estudio = nombre_estudio
    if email_estudio is not None:
        config.email_estudio = email_estudio
    db.commit()
    db.refresh(config)
    return obtener_config(db)


def actualizar_umbral_optimizador(db: Session, umbral: int) -> dict:
    config = _obtener_o_crear_config(db)
    config.umbral_instancias_optimizador = umbral
    db.commit()
    db.refresh(config)
    return {
        "umbral_instancias_optimizador": config.umbral_instancias_optimizador,
        "updated_at": config.updated_at.isoformat(),
    }


# ─── Reporte 1: Carga por empleado ───────────────────────────────────────────

def reporte_carga(db: Session, periodo: Optional[str], studio_id: int = None) -> dict:
    primer_dia, ultimo_dia, periodo_str = _parse_periodo(periodo)

    emp_filtros = [Empleado.activo == True]
    if studio_id is not None:
        emp_filtros.append(Empleado.studio_id == studio_id)
    empleados = db.query(Empleado).filter(*emp_filtros).all()
    resultado = []

    for emp in empleados:
        tareas_pendientes = db.query(Tarea).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.pendiente,
            Tarea.activo == True,
        ).count()

        tareas_en_curso = db.query(Tarea).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.en_progreso,
            Tarea.activo == True,
        ).count()

        tareas_completadas_periodo = db.query(Tarea).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.completada,
            Tarea.activo == True,
            Tarea.fecha_completada >= primer_dia,
            Tarea.fecha_completada <= ultimo_dia,
        ).count()

        # Horas reales desde sesiones de trabajo (TareaSesion) en el período
        sesiones = db.query(TareaSesion).filter(
            TareaSesion.empleado_id == emp.id,
            TareaSesion.minutos.isnot(None),
            TareaSesion.inicio >= datetime.combine(primer_dia, datetime.min.time()),
            TareaSesion.inicio <= datetime.combine(ultimo_dia, datetime.max.time()),
        ).all()
        horas_reales_sesiones = round(sum(s.minutos for s in sesiones if s.minutos) / 60, 2)

        if tareas_pendientes < 5:
            nivel_carga = "baja"
        elif tareas_pendientes <= 10:
            nivel_carga = "media"
        else:
            nivel_carga = "alta"

        resultado.append({
            "empleado_id": emp.id,
            "nombre": emp.nombre,
            "tareas_pendientes": tareas_pendientes,
            "tareas_en_curso": tareas_en_curso,
            "tareas_completadas_periodo": tareas_completadas_periodo,
            "horas_reales_sesiones": horas_reales_sesiones,
            "nivel_carga": nivel_carga,
        })

    resultado.sort(key=lambda x: ({"alta": 0, "media": 1, "baja": 2}[x["nivel_carga"]], -x["tareas_pendientes"]))
    return {"periodo": periodo_str, "empleados": resultado}


# ─── Reporte 2: Rentabilidad por cliente ─────────────────────────────────────

def reporte_rentabilidad(db: Session, periodo: Optional[str], studio_id: int = None) -> dict:
    primer_dia, ultimo_dia, periodo_str = _parse_periodo(periodo)
    config = _obtener_o_crear_config(db)

    if not config.tarifa_hora_pesos:
        return {
            "sin_configurar": True,
            "clientes": [],
            "periodo": periodo_str,
            "tarifa_hora": None,
        }

    tarifa = float(config.tarifa_hora_pesos)
    cli_filtros = [Cliente.activo == True]
    if studio_id is not None:
        cli_filtros.append(Cliente.studio_id == studio_id)
    clientes = db.query(Cliente).filter(*cli_filtros).all()

    # Índice: cliente_id → horas reales del mes (desde proceso_pasos_instancia)
    # JOIN: ProcesoPasoInstancia → ProcesoInstancia (por instancia_id) → cliente_id
    # Filtro: fecha_fin del paso dentro del período
    horas_por_cliente: dict[int, float] = {}

    inst_filtros = [
        ProcesoInstancia.cliente_id.isnot(None),
        ProcesoInstancia.fecha_fin.isnot(None),
        ProcesoInstancia.fecha_fin >= datetime.combine(primer_dia, datetime.min.time()),
        ProcesoInstancia.fecha_fin <= datetime.combine(ultimo_dia, datetime.max.time()),
    ]
    if studio_id is not None:
        inst_filtros.append(ProcesoInstancia.studio_id == studio_id)
    instancias_del_periodo = (
        db.query(ProcesoInstancia)
        .filter(*inst_filtros)
        .all()
    )

    for inst in instancias_del_periodo:
        pasos = db.query(ProcesoPasoInstancia).filter(
            ProcesoPasoInstancia.instancia_id == inst.id,
            ProcesoPasoInstancia.tiempo_real_minutos.isnot(None),
        ).all()
        minutos = sum(p.tiempo_real_minutos for p in pasos if p.tiempo_real_minutos)
        horas = minutos / 60
        horas_por_cliente[inst.cliente_id] = horas_por_cliente.get(inst.cliente_id, 0.0) + horas

    resultado = []
    for cliente in clientes:
        horas_reales = round(horas_por_cliente.get(cliente.id, 0.0), 2)
        costo_estimado = round(horas_reales * tarifa, 2)
        honorario = float(cliente.honorarios_mensuales) if cliente.honorarios_mensuales else None

        if honorario is not None:
            rentabilidad = round(honorario - costo_estimado, 2)
            margen_pct = round((rentabilidad / honorario) * 100, 1) if honorario > 0 else None
            alerta = margen_pct is not None and margen_pct < 0
            sin_honorario = False
        else:
            rentabilidad = None
            margen_pct = None
            alerta = False
            sin_honorario = True

        resultado.append({
            "cliente_id": cliente.id,
            "nombre": cliente.nombre,
            "honorario_mensual": honorario,
            "horas_reales": horas_reales,
            "costo_estimado": costo_estimado,
            "rentabilidad": rentabilidad,
            "margen_pct": margen_pct,
            "alerta": alerta,
            "sin_honorario": sin_honorario,
        })

    # Ordenar: alertas primero (margen_pct ASC), sin_honorario al final
    resultado.sort(key=lambda x: (
        x["sin_honorario"],
        x["margen_pct"] if x["margen_pct"] is not None else 999,
    ))

    return {"periodo": periodo_str, "tarifa_hora": tarifa, "clientes": resultado}


# ─── Reporte 3: Vencimientos del período ─────────────────────────────────────

def reporte_vencimientos(db: Session, periodo: Optional[str], estado: Optional[EstadoVencimiento], studio_id: int = None) -> dict:
    primer_dia, ultimo_dia, periodo_str = _parse_periodo(periodo)
    hoy = date.today()

    cli_filtros = []
    if studio_id is not None:
        cli_filtros.append(Cliente.studio_id == studio_id)
    clientes_idx = {c.id: c.nombre for c in db.query(Cliente).filter(*cli_filtros).all()}

    venc_filtros = [
        Vencimiento.fecha_vencimiento >= primer_dia,
        Vencimiento.fecha_vencimiento <= ultimo_dia,
    ]
    if studio_id is not None:
        venc_filtros.append(Vencimiento.studio_id == studio_id)
    query = db.query(Vencimiento).filter(*venc_filtros)
    if estado is not None:
        query = query.filter(Vencimiento.estado == estado)

    vencimientos = query.order_by(Vencimiento.fecha_vencimiento.asc()).all()

    items = []
    for v in vencimientos:
        dias_restantes = (v.fecha_vencimiento - hoy).days
        # alerta: vence en <= 7 días Y no está cumplido
        alerta = dias_restantes <= 7 and v.estado != EstadoVencimiento.cumplido
        items.append({
            "id": v.id,
            "cliente_nombre": clientes_idx.get(v.cliente_id, "Desconocido"),
            "cliente_id": v.cliente_id,
            "tipo": v.tipo.value,
            "descripcion": v.descripcion,
            "fecha_vencimiento": v.fecha_vencimiento.isoformat(),
            "dias_restantes": dias_restantes,
            "estado": v.estado.value,
            "alerta": alerta,
        })

    total = len(items)
    presentados = sum(1 for v in vencimientos if v.estado == EstadoVencimiento.cumplido)
    pendientes = sum(1 for v in vencimientos if v.estado == EstadoVencimiento.pendiente)
    vencidos = sum(1 for v in vencimientos if v.estado == EstadoVencimiento.vencido)
    en_riesgo = sum(1 for i in items if i["alerta"])

    return {
        "periodo": periodo_str,
        "resumen": {
            "total": total,
            "presentados": presentados,
            "pendientes": pendientes,
            "vencidos": vencidos,
            "en_riesgo": en_riesgo,
        },
        "vencimientos": items,
    }


# ─── Reporte 4: Eficiencia de procesos ───────────────────────────────────────

def reporte_procesos(db: Session, periodo: Optional[str], studio_id: int = None) -> dict:
    primer_dia, ultimo_dia, periodo_str = _parse_periodo(periodo)
    config = _obtener_o_crear_config(db)

    tmpl_filtros = [ProcesoTemplate.activo == True]
    if studio_id is not None:
        tmpl_filtros.append(ProcesoTemplate.studio_id == studio_id)
    templates = db.query(ProcesoTemplate).filter(*tmpl_filtros).all()
    emp_filtros = [Empleado.activo == True]
    if studio_id is not None:
        emp_filtros.append(Empleado.studio_id == studio_id)
    empleados_idx = {e.id: e.nombre for e in db.query(Empleado).filter(*emp_filtros).all()}

    resultado = []
    for template in templates:
        # Instancias completadas en el período
        instancias = db.query(ProcesoInstancia).filter(
            ProcesoInstancia.template_id == template.id,
            ProcesoInstancia.estado == EstadoInstancia.completado,
            ProcesoInstancia.fecha_fin.isnot(None),
            ProcesoInstancia.fecha_fin >= datetime.combine(primer_dia, datetime.min.time()),
            ProcesoInstancia.fecha_fin <= datetime.combine(ultimo_dia, datetime.max.time()),
        ).all()

        # Mínimo umbral_instancias_optimizador instancias completadas (configurable)
        umbral = config.umbral_instancias_optimizador if config and hasattr(config, 'umbral_instancias_optimizador') else 5
        if len(instancias) < umbral:
            continue

        # Duración estimada total del template (suma de pasos estimados)
        pasos_template = (
            db.query(ProcesoPasoTemplate)
            .filter(ProcesoPasoTemplate.template_id == template.id)
            .all()
        )
        duracion_estimada_min = sum(
            p.tiempo_estimado_minutos or 0 for p in pasos_template
        )

        # Duración real por instancia
        duraciones_reales = []
        por_empleado: dict[int, list[float]] = {}

        for inst in instancias:
            pasos_inst = db.query(ProcesoPasoInstancia).filter(
                ProcesoPasoInstancia.instancia_id == inst.id,
                ProcesoPasoInstancia.tiempo_real_minutos.isnot(None),
            ).all()
            total_real = sum(p.tiempo_real_minutos for p in pasos_inst if p.tiempo_real_minutos)
            if total_real > 0:
                duraciones_reales.append(total_real)

            if inst.creado_por:
                por_empleado.setdefault(inst.creado_por, []).append(total_real)

        if not duraciones_reales:
            continue

        duracion_real_promedio = round(sum(duraciones_reales) / len(duraciones_reales), 1)

        if duracion_estimada_min > 0:
            desviacion_pct = round(
                ((duracion_real_promedio - duracion_estimada_min) / duracion_estimada_min) * 100, 1
            )
        else:
            desviacion_pct = None

        alerta = desviacion_pct is not None and desviacion_pct > 20

        empleado_breakdown = [
            {
                "empleado_id": emp_id,
                "nombre": empleados_idx.get(emp_id, "Desconocido"),
                "promedio_min": round(sum(tiempos) / len(tiempos), 1),
                "instancias": len(tiempos),
            }
            for emp_id, tiempos in por_empleado.items()
            if tiempos
        ]
        empleado_breakdown.sort(key=lambda x: x["promedio_min"])

        resultado.append({
            "proceso_id": template.id,
            "nombre": template.nombre,
            "tipo": template.tipo.value,
            "instancias_completadas": len(instancias),
            "duracion_estimada_min": duracion_estimada_min,
            "duracion_real_promedio_min": duracion_real_promedio,
            "desviacion_pct": desviacion_pct,
            "alerta": alerta,
            "por_empleado": empleado_breakdown,
        })

    # Ordenar: mayor desviación primero
    resultado.sort(key=lambda x: (x["desviacion_pct"] is None, -(x["desviacion_pct"] or 0)))
    return {"periodo": periodo_str, "procesos": resultado}


# ─── Resumen ejecutivo ────────────────────────────────────────────────────────

def reporte_resumen(db: Session, periodo: Optional[str], studio_id: int = None) -> dict:
    _, _, periodo_str = _parse_periodo(periodo)
    hoy = date.today()
    primer_dia, ultimo_dia, _ = _parse_periodo(periodo)

    # Carga — empleados en alta
    emp_filtros = [Empleado.activo == True]
    if studio_id is not None:
        emp_filtros.append(Empleado.studio_id == studio_id)
    empleados = db.query(Empleado).filter(*emp_filtros).all()
    empleados_en_riesgo = 0
    empleado_mas_cargado = None
    max_pendientes = -1

    for emp in empleados:
        pendientes = db.query(Tarea).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado == EstadoTarea.pendiente,
            Tarea.activo == True,
        ).count()
        if pendientes > 10:
            empleados_en_riesgo += 1
        if pendientes > max_pendientes:
            max_pendientes = pendientes
            empleado_mas_cargado = f"{emp.nombre} — {pendientes} tareas"

    # Vencimientos en riesgo
    venc_filtros = [
        Vencimiento.fecha_vencimiento >= primer_dia,
        Vencimiento.fecha_vencimiento <= ultimo_dia,
    ]
    if studio_id is not None:
        venc_filtros.append(Vencimiento.studio_id == studio_id)
    vencimientos_periodo = db.query(Vencimiento).filter(*venc_filtros).all()
    en_riesgo_venc = sum(
        1 for v in vencimientos_periodo
        if (v.fecha_vencimiento - hoy).days <= 7 and v.estado != EstadoVencimiento.cumplido
    )
    vencen_hoy = sum(1 for v in vencimientos_periodo if v.fecha_vencimiento == hoy)

    # Rentabilidad — clientes en negativo (solo si hay tarifa configurada)
    clientes_en_negativo = 0
    peor_margen = None
    config = db.query(StudioConfig).first()
    if config and config.tarifa_hora_pesos:
        tarifa = float(config.tarifa_hora_pesos)
        cli_filtros = [Cliente.activo == True]
        if studio_id is not None:
            cli_filtros.append(Cliente.studio_id == studio_id)
        clientes = db.query(Cliente).filter(*cli_filtros).all()
        peor_margen_pct = None

        for cliente in clientes:
            if not cliente.honorarios_mensuales:
                continue
            honorario = float(cliente.honorarios_mensuales)
            inst_filtros = [
                ProcesoInstancia.cliente_id == cliente.id,
                ProcesoInstancia.fecha_fin.isnot(None),
                ProcesoInstancia.fecha_fin >= datetime.combine(primer_dia, datetime.min.time()),
                ProcesoInstancia.fecha_fin <= datetime.combine(ultimo_dia, datetime.max.time()),
            ]
            if studio_id is not None:
                inst_filtros.append(ProcesoInstancia.studio_id == studio_id)
            instancias = db.query(ProcesoInstancia).filter(*inst_filtros).all()
            minutos = 0
            for inst in instancias:
                pasos = db.query(ProcesoPasoInstancia).filter(
                    ProcesoPasoInstancia.instancia_id == inst.id,
                    ProcesoPasoInstancia.tiempo_real_minutos.isnot(None),
                ).all()
                minutos += sum(p.tiempo_real_minutos for p in pasos if p.tiempo_real_minutos)
            horas = minutos / 60
            costo = horas * tarifa
            margen = ((honorario - costo) / honorario * 100) if honorario > 0 else None
            if margen is not None and margen < 0:
                clientes_en_negativo += 1
                if peor_margen_pct is None or margen < peor_margen_pct:
                    peor_margen_pct = margen
                    peor_margen = {"cliente": cliente.nombre, "margen_pct": round(margen, 1)}

    # Procesos con desvío > 20% (solo con 5+ instancias)
    procesos_con_desvio = 0
    mayor_desvio = None
    max_desvio = -1

    tmpl_filtros2 = [ProcesoTemplate.activo == True]
    if studio_id is not None:
        tmpl_filtros2.append(ProcesoTemplate.studio_id == studio_id)
    templates = db.query(ProcesoTemplate).filter(*tmpl_filtros2).all()
    for template in templates:
        inst_f2 = [
            ProcesoInstancia.template_id == template.id,
            ProcesoInstancia.estado == EstadoInstancia.completado,
            ProcesoInstancia.fecha_fin.isnot(None),
            ProcesoInstancia.fecha_fin >= datetime.combine(primer_dia, datetime.min.time()),
            ProcesoInstancia.fecha_fin <= datetime.combine(ultimo_dia, datetime.max.time()),
        ]
        if studio_id is not None:
            inst_f2.append(ProcesoInstancia.studio_id == studio_id)
        instancias = db.query(ProcesoInstancia).filter(*inst_f2).all()
        if len(instancias) < 5:
            continue
        pasos_t = db.query(ProcesoPasoTemplate).filter(ProcesoPasoTemplate.template_id == template.id).all()
        estimado = sum(p.tiempo_estimado_minutos or 0 for p in pasos_t)
        if estimado <= 0:
            continue
        tiempos = []
        for inst in instancias:
            pasos_i = db.query(ProcesoPasoInstancia).filter(
                ProcesoPasoInstancia.instancia_id == inst.id,
                ProcesoPasoInstancia.tiempo_real_minutos.isnot(None),
            ).all()
            t = sum(p.tiempo_real_minutos for p in pasos_i if p.tiempo_real_minutos)
            if t > 0:
                tiempos.append(t)
        if not tiempos:
            continue
        promedio = sum(tiempos) / len(tiempos)
        desvio = ((promedio - estimado) / estimado) * 100
        if desvio > 20:
            procesos_con_desvio += 1
            if desvio > max_desvio:
                max_desvio = desvio
                mayor_desvio = {"proceso": template.nombre, "desvio_pct": round(desvio, 1)}

    auto_filtros = [Automatizacion.estado_revision == EstadoRevisionAutomatizacion.pendiente]
    if studio_id is not None:
        auto_filtros.append(Automatizacion.studio_id == studio_id)
    automatizaciones_pendientes = db.query(Automatizacion).filter(*auto_filtros).count()

    # Cobertura de SOPs
    cobertura_sops = _calcular_cobertura_sops(db, studio_id)

    return {
        "periodo": periodo_str,
        "carga": {
            "empleados_en_riesgo": empleados_en_riesgo,
            "empleado_mas_cargado": empleado_mas_cargado,
        },
        "rentabilidad": {
            "clientes_en_negativo": clientes_en_negativo,
            "peor_margen": peor_margen,
        },
        "vencimientos": {
            "en_riesgo": en_riesgo_venc,
            "vencen_hoy": vencen_hoy,
        },
        "procesos": {
            "procesos_con_desvio": procesos_con_desvio,
            "mayor_desvio": mayor_desvio,
        },
        "automatizaciones_pendientes_revision": automatizaciones_pendientes,
        "cobertura_sops": cobertura_sops,
    }


def _calcular_cobertura_sops(db: Session, studio_id: int = None) -> dict:
    """Calcula cobertura de SOPs sobre procesos activos."""
    from datetime import datetime, timedelta
    hoy = datetime.utcnow()
    hace_90_dias = hoy - timedelta(days=90)

    tmpl_f = [ProcesoTemplate.activo == True]
    if studio_id is not None:
        tmpl_f.append(ProcesoTemplate.studio_id == studio_id)
    procesos_activos = db.query(ProcesoTemplate).filter(*tmpl_f).all()
    procesos_totales = len(procesos_activos)

    # Procesos con al menos un SOP activo vinculado
    procesos_con_sop = 0
    for proc in procesos_activos:
        sop_f = [SopDocumento.proceso_id == proc.id, SopDocumento.estado == EstadoSop.activo]
        if studio_id is not None:
            sop_f.append(SopDocumento.studio_id == studio_id)
        tiene_sop = db.query(SopDocumento).filter(*sop_f).first()
        if tiene_sop:
            procesos_con_sop += 1

    procesos_sin_sop = procesos_totales - procesos_con_sop
    porcentaje = round((procesos_con_sop / procesos_totales) * 100) if procesos_totales > 0 else 0

    # SOPs próximos a revisión (sin fecha o fecha > 90 días)
    sop_a_f = [SopDocumento.estado == EstadoSop.activo]
    if studio_id is not None:
        sop_a_f.append(SopDocumento.studio_id == studio_id)
    sops_activos = db.query(SopDocumento).filter(*sop_a_f).all()
    sops_proximos_revision = []
    for sop in sops_activos:
        if sop.fecha_ultima_revision is None or sop.fecha_ultima_revision <= hace_90_dias:
            sops_proximos_revision.append({
                "id": sop.id,
                "titulo": sop.titulo,
                "fecha_ultima_revision": sop.fecha_ultima_revision.isoformat() if sop.fecha_ultima_revision else None,
            })

    # SOPs activos sin responsable
    sops_sin_responsable = [
        {"id": sop.id, "titulo": sop.titulo}
        for sop in sops_activos
        if not sop.empleado_responsable_id
    ]

    return {
        "procesos_totales": procesos_totales,
        "procesos_con_sop": procesos_con_sop,
        "procesos_sin_sop": procesos_sin_sop,
        "porcentaje_cobertura": porcentaje,
        "sops_proximos_revision": sops_proximos_revision,
        "sops_sin_responsable": sops_sin_responsable,
    }


# ─── Diagnóstico de Madurez ───────────────────────────────────────────────────

def reporte_madurez(db: Session, studio_id: int = None) -> dict:
    """Calcula la etapa de madurez del estudio según SYSTEMology."""
    from datetime import datetime, timedelta

    hoy = datetime.utcnow()
    hace_90_dias = hoy - timedelta(days=90)

    # Indicadores
    tmpl_f = [ProcesoTemplate.activo == True]
    if studio_id is not None:
        tmpl_f.append(ProcesoTemplate.studio_id == studio_id)
    procesos_activos = db.query(ProcesoTemplate).filter(*tmpl_f).count()

    inst_f = [ProcesoInstancia.estado == EstadoInstancia.completado, ProcesoInstancia.fecha_fin.isnot(None), ProcesoInstancia.fecha_fin >= hace_90_dias]
    if studio_id is not None:
        inst_f.append(ProcesoInstancia.studio_id == studio_id)
    instancias_90d = db.query(ProcesoInstancia).filter(*inst_f).count()

    sop_f = [SopDocumento.estado == EstadoSop.activo]
    if studio_id is not None:
        sop_f.append(SopDocumento.studio_id == studio_id)
    sops_activos = db.query(SopDocumento).filter(*sop_f).count()

    auto_f = [Automatizacion.estado_revision == EstadoRevisionAutomatizacion.aprobada]
    if studio_id is not None:
        auto_f.append(Automatizacion.studio_id == studio_id)
    automatizaciones_aprobadas = db.query(Automatizacion).filter(*auto_f).count()

    # Eficiencia promedio últimos 90 días
    eficiencia_promedio = _calcular_eficiencia_promedio(db, hace_90_dias, studio_id)

    # Determinar etapa — umbrales ajustados para estudios de 1-3 personas
    if procesos_activos >= 3 and sops_activos >= 1 and automatizaciones_aprobadas >= 1 and eficiencia_promedio is not None and eficiencia_promedio >= 0.80:
        etapa_num = 4
        etapa_nombre = "Saleable"
        descripcion_etapa = "Tu estudio opera de forma independiente a tu presencia. Los procesos, SOPs y automatizaciones permiten delegar o transferir el negocio."
        proximos_pasos = [
            {"descripcion": "Documentar los KPIs clave del estudio (margen por cliente, tasa de completado)", "horas_estimadas": 4, "prioridad": "alta"},
            {"descripcion": "Preparar un manual de operaciones resumido para incorporar personal o socios", "horas_estimadas": 8, "prioridad": "media"},
            {"descripcion": "Evaluar servicios adicionales que escalen sin agregar horas proporcionales", "horas_estimadas": 2, "prioridad": "baja"},
        ]
    elif procesos_activos >= 3 and sops_activos >= 1 and automatizaciones_aprobadas >= 1:
        etapa_num = 3
        etapa_nombre = "Scalable"
        descripcion_etapa = "Tenés procesos, SOPs y automatizaciones activas. El estudio puede crecer sin que todo dependa solo de vos."
        proximos_pasos = [
            {"descripcion": "Mejorar la eficiencia promedio de procesos al 80% — revisá los pasos con mayor desvío", "horas_estimadas": 3, "prioridad": "alta"},
            {"descripcion": "Revisar y optimizar las automatizaciones existentes en n8n", "horas_estimadas": 2, "prioridad": "media"},
            {"descripcion": "Registrar satisfacción de clientes al completar cada proceso", "horas_estimadas": 1, "prioridad": "baja"},
        ]
    elif procesos_activos >= 2 or sops_activos >= 1:
        etapa_num = 2
        etapa_nombre = "Stationary"
        descripcion_etapa = "Empezaste a sistematizar. Tenés algunos procesos documentados o SOPs. El próximo paso es automatizar una tarea repetitiva."
        proximos_pasos = [
            {"descripcion": "Identificar la tarea más repetitiva y crear una automatización en n8n", "horas_estimadas": 4, "prioridad": "alta"},
            {"descripcion": "Vincular los SOPs activos a sus procesos correspondientes", "horas_estimadas": 2, "prioridad": "alta"},
            {"descripcion": "Documentar al menos 3 procesos del estudio con sus pasos y tiempos estimados", "horas_estimadas": 3, "prioridad": "media"},
        ]
    else:
        etapa_num = 1
        etapa_nombre = "Survival"
        descripcion_etapa = "El estudio todavía opera de forma reactiva. Todo depende de la memoria y disponibilidad del contador. Es el momento de empezar a documentar."
        proximos_pasos = [
            {"descripcion": "Crear los primeros 2-3 procesos en el sistema (ej: liquidación de IVA, onboarding de cliente)", "horas_estimadas": 3, "prioridad": "alta"},
            {"descripcion": "Generar el primer SOP del estudio desde la sección /sop", "horas_estimadas": 2, "prioridad": "alta"},
            {"descripcion": "Registrar instancias de procesos durante 2 semanas para obtener tiempos reales", "horas_estimadas": 1, "prioridad": "media"},
        ]

    return {
        "etapa": {
            "numero": etapa_num,
            "nombre": etapa_nombre,
            "descripcion": descripcion_etapa,
        },
        "indicadores": {
            "procesos_activos": procesos_activos,
            "instancias_completadas_90d": instancias_90d,
            "sops_activos": sops_activos,
            "automatizaciones_aprobadas": automatizaciones_aprobadas,
            "eficiencia_promedio": round(eficiencia_promedio, 2) if eficiencia_promedio is not None else None,
        },
        "proximos_pasos": proximos_pasos,
    }


def _calcular_eficiencia_promedio(db: Session, desde: "datetime", studio_id: int = None) -> Optional[float]:
    """Eficiencia = tiempo_estimado / tiempo_real. Retorna None si no hay datos."""
    tmpl_f = [ProcesoTemplate.activo == True]
    if studio_id is not None:
        tmpl_f.append(ProcesoTemplate.studio_id == studio_id)
    templates = db.query(ProcesoTemplate).filter(*tmpl_f).all()
    eficiencias = []

    for template in templates:
        if not template.tiempo_estimado_minutos:
            continue

        inst_f = [
            ProcesoInstancia.template_id == template.id,
            ProcesoInstancia.estado == EstadoInstancia.completado,
            ProcesoInstancia.fecha_inicio.isnot(None),
            ProcesoInstancia.fecha_fin.isnot(None),
            ProcesoInstancia.fecha_fin >= desde,
        ]
        if studio_id is not None:
            inst_f.append(ProcesoInstancia.studio_id == studio_id)
        instancias = db.query(ProcesoInstancia).filter(*inst_f).all()

        for inst in instancias:
            real = (inst.fecha_fin - inst.fecha_inicio).total_seconds() / 60
            if real > 0:
                eficiencias.append(template.tiempo_estimado_minutos / real)

    return sum(eficiencias) / len(eficiencias) if eficiencias else None


# ─── Reporte D2: Rentabilidad por tipo de cliente ────────────────────────────

def rentabilidad_por_tipo(db: Session, studio_id: int) -> list[dict]:
    """
    Agrupa la rentabilidad por tipo_cliente.
    Para cada tipo: cantidad de clientes, honorario promedio y margen promedio.
    """
    from models.rentabilidad import RentabilidadMensual

    tipos = list(TipoCliente)
    resultado = []

    for tipo in tipos:
        cli_f = [
            Cliente.studio_id == studio_id,
            Cliente.activo == True,
            Cliente.tipo_cliente == tipo,
        ]
        clientes = db.query(Cliente).filter(*cli_f).all()
        if not clientes:
            continue

        ids = [c.id for c in clientes]
        honorario_promedio = (
            sum(float(c.honorarios_mensuales or c.honorario_base or 0) for c in clientes) / len(clientes)
        )

        # Margen promedio desde snapshots de rentabilidad
        snapshots = (
            db.query(RentabilidadMensual)
            .filter(
                RentabilidadMensual.studio_id == studio_id,
                RentabilidadMensual.cliente_id.in_(ids),
            )
            .all()
        )
        margenes = [
            float(s.profit_margin_percentage)
            for s in snapshots
            if s.profit_margin_percentage is not None
        ]
        margen_promedio = round(sum(margenes) / len(margenes), 2) if margenes else 0.0

        clientes_out = [
            {
                "cliente_id": c.id,
                "nombre": c.nombre,
                "honorarios_mensuales": float(c.honorarios_mensuales or 0),
                "honorario_base": float(c.honorario_base or 0),
            }
            for c in clientes
        ]

        resultado.append({
            "tipo_cliente": tipo.value,
            "cantidad_clientes": len(clientes),
            "honorario_promedio": round(honorario_promedio, 2),
            "margen_promedio": margen_promedio,
            "clientes": clientes_out,
        })

    return resultado


# ─── Reporte D3: Tiempo real por cliente ─────────────────────────────────────

def tiempo_por_cliente(
    db: Session,
    studio_id: int,
    fecha_desde: date,
    fecha_hasta: date,
) -> list[dict]:
    """
    Calcula tiempo dedicado por cliente entre fecha_desde y fecha_hasta.
    Usa tarea_sesiones → tareas → clientes.
    """
    desde_dt = datetime.combine(fecha_desde, datetime.min.time())
    hasta_dt = datetime.combine(fecha_hasta, datetime.max.time())

    # Traer todas las sesiones del período del studio
    sesiones = (
        db.query(TareaSesion, Tarea)
        .join(Tarea, TareaSesion.tarea_id == Tarea.id)
        .filter(
            Tarea.studio_id == studio_id,
            Tarea.cliente_id.isnot(None),
            TareaSesion.minutos.isnot(None),
            TareaSesion.inicio >= desde_dt,
            TareaSesion.inicio <= hasta_dt,
        )
        .all()
    )

    # Agrupar por cliente_id
    from collections import defaultdict
    minutos_por_cliente: dict[int, int] = defaultdict(int)
    for sesion, tarea in sesiones:
        minutos_por_cliente[tarea.cliente_id] += sesion.minutos or 0

    if not minutos_por_cliente:
        return []

    # Traer clientes involucrados
    cliente_ids = list(minutos_por_cliente.keys())
    clientes = (
        db.query(Cliente)
        .filter(Cliente.id.in_(cliente_ids), Cliente.studio_id == studio_id)
        .all()
    )
    clientes_map = {c.id: c for c in clientes}

    # Contar tareas completadas y activas por cliente en el período
    resultado = []
    for cliente_id, minutos in minutos_por_cliente.items():
        cliente = clientes_map.get(cliente_id)
        if not cliente:
            continue

        tareas_completadas = db.query(Tarea).filter(
            Tarea.studio_id == studio_id,
            Tarea.cliente_id == cliente_id,
            Tarea.estado == EstadoTarea.completada,
            Tarea.fecha_completada >= fecha_desde,
            Tarea.fecha_completada <= fecha_hasta,
        ).count()

        tareas_activas = db.query(Tarea).filter(
            Tarea.studio_id == studio_id,
            Tarea.cliente_id == cliente_id,
            Tarea.estado != EstadoTarea.completada,
            Tarea.activo == True,
        ).count()

        horas_totales = round(minutos / 60, 2)
        honorario = float(cliente.honorarios_mensuales or 0)
        costo_hora = round(Decimal(str(honorario)) / Decimal(str(horas_totales)), 2) if horas_totales > 0 else None

        resultado.append({
            "cliente_id": cliente_id,
            "cliente_nombre": cliente.nombre,
            "tipo_cliente": cliente.tipo_cliente.value,
            "minutos_totales": minutos,
            "horas_totales": horas_totales,
            "tareas_completadas": tareas_completadas,
            "tareas_activas": tareas_activas,
            "honorario_mensual": honorario,
            "costo_hora_estimado": float(costo_hora) if costo_hora is not None else None,
        })

    resultado.sort(key=lambda x: -x["minutos_totales"])
    return resultado

