"""
Construye el contexto de datos del usuario para el system prompt del asistente.
La desambiguación ocurre en service.py, no aquí.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.documento import Documento, EstadoDocumento
from models.empleado import Empleado
from models.tarea import EstadoTarea, Tarea
from models.vencimiento import EstadoVencimiento, Vencimiento


def contexto_contador(db: Session, empleado_id: int) -> dict:
    """Datos visibles para un contador: solo sus clientes asignados."""
    empleado = db.query(Empleado).filter(Empleado.id == empleado_id).first()
    if not empleado:
        return {}

    hoy = date.today()
    proximos_7 = hoy + timedelta(days=7)

    # Clientes asignados
    clientes = db.query(Cliente).filter(
        Cliente.contador_asignado_id == empleado_id,
        Cliente.activo == True,
    ).all()
    cliente_ids = [c.id for c in clientes]

    # Tareas del día (fecha_limite = hoy o pendientes urgentes)
    tareas_hoy = db.query(Tarea).filter(
        Tarea.cliente_id.in_(cliente_ids),
        Tarea.estado.in_([EstadoTarea.pendiente, EstadoTarea.en_progreso]),
        Tarea.activo == True,
    ).order_by(Tarea.fecha_limite).limit(10).all()

    # Vencimientos próximos 7 días
    vencimientos = db.query(Vencimiento, Cliente).join(
        Cliente, Vencimiento.cliente_id == Cliente.id
    ).filter(
        Vencimiento.cliente_id.in_(cliente_ids),
        Vencimiento.estado == EstadoVencimiento.pendiente,
        Vencimiento.fecha_vencimiento <= proximos_7,
    ).order_by(Vencimiento.fecha_vencimiento).all()

    # Documentos pendientes de revisión
    docs_pendientes = db.query(Documento).filter(
        Documento.cliente_id.in_(cliente_ids),
        Documento.estado == EstadoDocumento.pendiente,
        Documento.activo == True,
    ).count()

    return {
        "empleado_nombre": empleado.nombre,
        "empleado_rol": empleado.rol.value if hasattr(empleado.rol, "value") else str(empleado.rol),
        "clientes_asignados": [{"id": c.id, "nombre": c.nombre, "cuit": c.cuit_cuil} for c in clientes],
        "tareas_activas": [
            {
                "id": t.id,
                "descripcion": t.descripcion,
                "cliente_id": t.cliente_id,
                "estado": t.estado.value if hasattr(t.estado, "value") else str(t.estado),
                "fecha_limite": t.fecha_limite.isoformat() if t.fecha_limite else None,
            }
            for t in tareas_hoy
        ],
        "vencimientos_proximos": [
            {
                "cliente": v[1].nombre,
                "tipo": v[0].tipo.value if hasattr(v[0].tipo, "value") else str(v[0].tipo),
                "fecha": v[0].fecha_vencimiento.isoformat(),
                "dias_restantes": (v[0].fecha_vencimiento - hoy).days,
            }
            for v in vencimientos
        ],
        "documentos_pendientes_revision": docs_pendientes,
    }


def contexto_dueno(db: Session) -> dict:
    """Datos visibles para el dueño del estudio: todo el estudio."""
    from models.alerta import AlertaVencimiento
    from models.empleado import Empleado

    hoy = date.today()
    proximos_7 = hoy + timedelta(days=7)

    empleados = db.query(Empleado).filter(Empleado.activo == True).all()

    resumen_equipo = []
    for emp in empleados:
        cliente_ids = [
            c.id for c in db.query(Cliente).filter(
                Cliente.contador_asignado_id == emp.id,
                Cliente.activo == True,
            ).all()
        ]
        tareas_pend = db.query(Tarea).filter(
            Tarea.cliente_id.in_(cliente_ids),
            Tarea.estado == EstadoTarea.pendiente,
            Tarea.activo == True,
        ).count() if cliente_ids else 0
        venc_prox = db.query(Vencimiento).filter(
            Vencimiento.cliente_id.in_(cliente_ids),
            Vencimiento.estado == EstadoVencimiento.pendiente,
            Vencimiento.fecha_vencimiento <= proximos_7,
        ).count() if cliente_ids else 0
        resumen_equipo.append({
            "nombre": emp.nombre,
            "clientes_asignados": len(cliente_ids),
            "tareas_pendientes": tareas_pend,
            "vencimientos_proximos_7d": venc_prox,
        })

    alertas = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.resuelta_at == None,
        AlertaVencimiento.nivel == "critica",
    ).count()

    clientes_riesgo = db.query(Cliente).filter(
        Cliente.activo == True,
        Cliente.risk_level == "rojo",
    ).count()

    return {
        "resumen_equipo": resumen_equipo,
        "alertas_criticas_activas": alertas,
        "clientes_en_riesgo_rojo": clientes_riesgo,
    }


def contexto_cliente(db: Session, cliente_id: int) -> dict:
    """Datos visibles para un cliente del estudio."""
    hoy = date.today()

    cliente = db.query(Cliente).filter(Cliente.id == cliente_id, Cliente.activo == True).first()
    if not cliente:
        return {}

    proximo_venc = (
        db.query(Vencimiento)
        .filter(
            Vencimiento.cliente_id == cliente_id,
            Vencimiento.estado == EstadoVencimiento.pendiente,
            Vencimiento.fecha_vencimiento >= hoy,
        )
        .order_by(Vencimiento.fecha_vencimiento)
        .first()
    )

    docs = db.query(Documento).filter(
        Documento.cliente_id == cliente_id,
        Documento.activo == True,
    ).all()
    docs_recibidos = [d.nombre_original for d in docs if d.estado.value != "pendiente"]
    docs_pendientes_list = [d.nombre_original for d in docs if d.estado.value == "pendiente"]

    return {
        "nombre_cliente": cliente.nombre,
        "cuit_cliente": cliente.cuit_cuil,
        "docs_recibidos": docs_recibidos,
        "docs_pendientes": docs_pendientes_list,
        "proximo_vencimiento": proximo_venc.fecha_vencimiento.isoformat() if proximo_venc else None,
        "estado_proceso": "en curso",
    }
