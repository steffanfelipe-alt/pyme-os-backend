from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.empleado import Empleado
from models.tarea import EstadoTarea, Tarea

# Constantes de negocio
HORAS_DEFAULT_POR_TAREA = 2.0   # si una tarea no tiene horas_estimadas
HORAS_DIARIAS_LABORALES = 8.0
UMBRAL_SOBRECARGADO = 0.90      # > 90% = sobrecargado
UMBRAL_OCUPADO = 0.70           # > 70% = ocupado, <= 70% = disponible

# Feriados nacionales argentinos 2026 (hardcodeado para el MVP)
FERIADOS_2026 = {
    date(2026, 1, 1),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 3, 24),
    date(2026, 4, 2),
    date(2026, 4, 3),
    date(2026, 5, 1),
    date(2026, 5, 25),
    date(2026, 6, 15),
    date(2026, 6, 20),
    date(2026, 7, 9),
    date(2026, 8, 17),
    date(2026, 10, 12),
    date(2026, 11, 20),
    date(2026, 12, 8),
    date(2026, 12, 25),
}


def _dias_habiles(desde: date, hasta: date) -> int:
    """Cuenta días hábiles entre dos fechas, excluyendo fines de semana y feriados."""
    dias = 0
    actual = desde
    while actual <= hasta:
        if actual.weekday() < 5 and actual not in FERIADOS_2026:
            dias += 1
        actual += timedelta(days=1)
    return dias


def obtener_panel_carga(db: Session, dias: int = 14) -> list[dict]:
    """
    Retorna el panel de carga para todos los empleados activos.
    dias: ventana de análisis (7, 14 o 30 días desde hoy).
    """
    hoy = date.today()
    hasta = hoy + timedelta(days=dias)
    dias_habiles = _dias_habiles(hoy, hasta)
    horas_disponibles = dias_habiles * HORAS_DIARIAS_LABORALES

    empleados = db.query(Empleado).filter(Empleado.activo == True).all()

    resultado = []
    for emp in empleados:
        tareas = db.query(Tarea).filter(
            Tarea.empleado_id == emp.id,
            Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
            Tarea.activo == True,
            Tarea.fecha_limite >= hoy,
            Tarea.fecha_limite <= hasta,
        ).all()

        horas_comprometidas = sum(
            (t.horas_estimadas or HORAS_DEFAULT_POR_TAREA) for t in tareas
        )

        porcentaje = (
            horas_comprometidas / horas_disponibles
            if horas_disponibles > 0 else 0.0
        )

        if porcentaje > UMBRAL_SOBRECARGADO:
            nivel = "sobrecargado"
        elif porcentaje > UMBRAL_OCUPADO:
            nivel = "ocupado"
        else:
            nivel = "disponible"

        resultado.append({
            "empleado_id": emp.id,
            "nombre": emp.nombre,
            "email": emp.email,
            "horas_comprometidas": round(horas_comprometidas, 1),
            "horas_disponibles": round(horas_disponibles, 1),
            "porcentaje_carga": round(porcentaje * 100, 1),
            "nivel": nivel,
            "cantidad_tareas": len(tareas),
            "tareas_sin_horas_estimadas": sum(
                1 for t in tareas if t.horas_estimadas is None
            ),
        })

    orden = {"sobrecargado": 0, "ocupado": 1, "disponible": 2}
    resultado.sort(key=lambda x: (orden[x["nivel"]], -x["horas_comprometidas"]))
    return resultado


def obtener_detalle_empleado(db: Session, empleado_id: int, dias: int = 14) -> dict:
    """Detalle de carga de un empleado con lista de tareas por cliente."""
    emp = db.query(Empleado).filter(
        Empleado.id == empleado_id,
        Empleado.activo == True,
    ).first()
    if not emp:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")

    hoy = date.today()
    hasta = hoy + timedelta(days=dias)
    dias_habiles = _dias_habiles(hoy, hasta)
    horas_disponibles = dias_habiles * HORAS_DIARIAS_LABORALES

    tareas = db.query(Tarea).filter(
        Tarea.empleado_id == emp.id,
        Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
        Tarea.activo == True,
        Tarea.fecha_limite >= hoy,
        Tarea.fecha_limite <= hasta,
    ).all()

    clientes_ids = {t.cliente_id for t in tareas}
    clientes = {
        c.id: c.nombre
        for c in db.query(Cliente).filter(Cliente.id.in_(clientes_ids)).all()
    } if clientes_ids else {}

    tareas_detalle = []
    for t in tareas:
        tareas_detalle.append({
            "tarea_id": t.id,
            "titulo": t.titulo,
            "cliente": clientes.get(t.cliente_id, "Desconocido"),
            "cliente_id": t.cliente_id,
            "fecha_limite": t.fecha_limite.isoformat(),
            "estado": t.estado.value,
            "horas_estimadas": t.horas_estimadas or HORAS_DEFAULT_POR_TAREA,
            "prioridad": t.prioridad.value,
        })

    horas_comprometidas = sum(t["horas_estimadas"] for t in tareas_detalle)
    porcentaje = (
        horas_comprometidas / horas_disponibles
        if horas_disponibles > 0 else 0.0
    )

    if porcentaje > UMBRAL_SOBRECARGADO:
        nivel = "sobrecargado"
    elif porcentaje > UMBRAL_OCUPADO:
        nivel = "ocupado"
    else:
        nivel = "disponible"

    return {
        "empleado_id": emp.id,
        "nombre": emp.nombre,
        "email": emp.email,
        "horas_comprometidas": round(horas_comprometidas, 1),
        "horas_disponibles": round(horas_disponibles, 1),
        "porcentaje_carga": round(porcentaje * 100, 1),
        "nivel": nivel,
        "tareas": tareas_detalle,
    }


def obtener_resumen_carga(db: Session) -> dict:
    """Resumen ejecutivo para el widget del dashboard."""
    panel = obtener_panel_carga(db, dias=14)
    return {
        "periodo_dias": 14,
        "total_empleados": len(panel),
        "sobrecargados": sum(1 for e in panel if e["nivel"] == "sobrecargado"),
        "ocupados": sum(1 for e in panel if e["nivel"] == "ocupado"),
        "disponibles": sum(1 for e in panel if e["nivel"] == "disponible"),
        "tareas_sin_asignar": _contar_tareas_sin_asignar(db, 14),
    }


def _contar_tareas_sin_asignar(db: Session, dias: int) -> int:
    """Tareas pendientes sin empleado asignado con vencimiento en el período."""
    hoy = date.today()
    hasta = hoy + timedelta(days=dias)
    return db.query(Tarea).filter(
        Tarea.empleado_id == None,
        Tarea.estado == EstadoTarea.pendiente,
        Tarea.activo == True,
        Tarea.fecha_limite >= hoy,
        Tarea.fecha_limite <= hasta,
    ).count()
