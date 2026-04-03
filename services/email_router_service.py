"""
Routing inteligente de emails: determina a qué empleado asignar cada email
según la clasificación, el remitente y los roles disponibles en el estudio.
"""
import logging
from typing import Any

from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.email_entrante import EmailEntrante
from models.empleado import Empleado, RolEmpleado

logger = logging.getLogger("pymeos")


def buscar_empleado_por_rol(rol: str, db: Session) -> int | None:
    """Retorna el id del primer empleado activo con ese rol."""
    empleado = (
        db.query(Empleado)
        .filter(Empleado.rol == rol, Empleado.activo == True)
        .first()
    )
    return empleado.id if empleado else None


def notificar_dueno(email: EmailEntrante, db: Session) -> None:
    """
    Crea una copia del email asignada al dueño cuando la urgencia es alta.
    Si el email ya está asignado al dueño no duplica.
    """
    dueno_id = buscar_empleado_por_rol(RolEmpleado.dueno, db)
    if dueno_id is None or email.asignado_a == dueno_id:
        return

    copia = EmailEntrante(
        remitente=email.remitente,
        asunto=f"[URGENTE] {email.asunto or ''}",
        cuerpo_texto=email.cuerpo_texto,
        cuerpo_html=email.cuerpo_html,
        tiene_adjuntos=email.tiene_adjuntos,
        fecha_recibido=email.fecha_recibido,
        gmail_message_id=None,  # copia interna, sin message_id único
        categoria=email.categoria,
        urgencia=email.urgencia,
        resumen=email.resumen,
        remitente_tipo=email.remitente_tipo,
        confianza_clasificacion=email.confianza_clasificacion,
        requiere_respuesta=False,
        requiere_revision_manual=True,
        motivo_revision="urgencia_alta",
        cliente_id=email.cliente_id,
        asignado_a=dueno_id,
        estado="no_leido",
    )
    db.add(copia)
    db.flush()


def determinar_destinatario(clasificacion: dict[str, Any], db: Session) -> int | None:
    """
    Determina el empleado_id al que asignar el email.
    Orden de prioridad:
    1. Si hay cliente registrado → su contador asignado
    2. Routing por categoría → rol correspondiente
    3. Sin match → None (bandeja general)
    """
    cliente_cuit = clasificacion.get("cliente_cuit")
    categoria = clasificacion.get("categoria")

    # 1. Remitente es un cliente registrado → va a su contador
    if cliente_cuit:
        cliente = (
            db.query(Cliente)
            .filter(Cliente.cuit_cuil == cliente_cuit, Cliente.activo == True)
            .first()
        )
        if cliente and cliente.contador_asignado_id:
            return cliente.contador_asignado_id

    # 2. Routing por categoría
    routing_por_categoria = {
        "postulacion_laboral": RolEmpleado.rrhh,
        "solicitud_licencia": RolEmpleado.rrhh,
        "consulta_interna": RolEmpleado.dueno,
        "proveedor": RolEmpleado.administrativo,
        "notificacion_afip": RolEmpleado.dueno,
    }
    if categoria in routing_por_categoria:
        rol_destino = routing_por_categoria[categoria]
        return buscar_empleado_por_rol(rol_destino, db)

    # 3. Sin match → bandeja general
    return None


def procesar_email_entrante(email: EmailEntrante, clasificacion: dict[str, Any], db: Session) -> None:
    """
    Aplica clasificación y routing a un EmailEntrante ya persistido.
    Actualiza sus campos en la misma sesión.
    """
    email.categoria = clasificacion.get("categoria")
    email.urgencia = clasificacion.get("urgencia")
    email.resumen = clasificacion.get("resumen")
    email.remitente_tipo = clasificacion.get("remitente_tipo")
    email.confianza_clasificacion = clasificacion.get("confianza")
    email.requiere_respuesta = clasificacion.get("requiere_respuesta", False)
    email.borrador_respuesta = clasificacion.get("borrador_respuesta")
    email.requiere_revision_manual = clasificacion.get("requiere_revision_manual", False)
    email.motivo_revision = clasificacion.get("motivo_revision")

    # Vincular cliente si se detectó CUIT
    cliente_cuit = clasificacion.get("cliente_cuit")
    if cliente_cuit:
        cliente = (
            db.query(Cliente)
            .filter(Cliente.cuit_cuil == cliente_cuit, Cliente.activo == True)
            .first()
        )
        if cliente:
            email.cliente_id = cliente.id

    # Routing
    email.asignado_a = determinar_destinatario(clasificacion, db)

    db.flush()

    # Si urgencia alta → copia al dueño
    if email.urgencia == "alta":
        notificar_dueno(email, db)
