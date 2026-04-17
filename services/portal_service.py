"""E1 — Portal de tareas para clientes (token público)."""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.portal_token import PortalToken
from models.tarea import EstadoTarea, Tarea


def generar_token_portal(db: Session, cliente_id: int, studio_id: int, dias_validez: int = 30) -> PortalToken:
    """Genera (o reutiliza el activo) un token de portal para un cliente."""
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id, Cliente.studio_id == studio_id
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    # Desactivar tokens anteriores del mismo cliente
    db.query(PortalToken).filter(
        PortalToken.cliente_id == cliente_id,
        PortalToken.studio_id == studio_id,
        PortalToken.activo == True,
    ).update({"activo": False})

    token = PortalToken(
        studio_id=studio_id,
        cliente_id=cliente_id,
        token=uuid.uuid4().hex,
        activo=True,
        expira_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=dias_validez),
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def obtener_tareas_por_token(db: Session, token: str) -> dict:
    """Retorna las tareas del cliente asociadas al token (endpoint público)."""
    portal = db.query(PortalToken).filter(
        PortalToken.token == token,
        PortalToken.activo == True,
    ).first()

    if not portal:
        raise HTTPException(status_code=404, detail="Token inválido o expirado")

    if portal.expira_at and portal.expira_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Token expirado")

    tareas = db.query(Tarea).filter(
        Tarea.cliente_id == portal.cliente_id,
        Tarea.studio_id == portal.studio_id,
        Tarea.activo == True,
    ).all()

    cliente = db.query(Cliente).filter(Cliente.id == portal.cliente_id).first()

    return {
        "cliente_nombre": cliente.nombre if cliente else "",
        "tareas": [
            {
                "id": t.id,
                "titulo": t.titulo,
                "tipo": t.tipo.value,
                "prioridad": t.prioridad.value,
                "estado": t.estado.value,
                "fecha_limite": t.fecha_limite.isoformat() if t.fecha_limite else None,
            }
            for t in tareas
        ],
        "pendientes": sum(1 for t in tareas if t.estado == EstadoTarea.pendiente),
        "en_progreso": sum(1 for t in tareas if t.estado == EstadoTarea.en_progreso),
        "completadas": sum(1 for t in tareas if t.estado == EstadoTarea.completada),
    }


def revocar_token(db: Session, cliente_id: int, studio_id: int) -> dict:
    """Desactiva todos los tokens activos de un cliente."""
    count = db.query(PortalToken).filter(
        PortalToken.cliente_id == cliente_id,
        PortalToken.studio_id == studio_id,
        PortalToken.activo == True,
    ).update({"activo": False})
    db.commit()
    return {"revocados": count}
