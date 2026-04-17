"""E2 — Solicitud automática de documentos faltantes."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.alerta import AlertaVencimiento, DocumentoRequerido
from models.solicitud_documento import EstadoSolicitud, SolicitudDocumentoAuto
from models.vencimiento import Vencimiento


def solicitar_documentos_faltantes(db: Session, studio_id: int) -> list[dict]:
    """
    Para cada alerta activa con documentos faltantes, genera solicitudes
    de documentos que aún no han sido solicitadas.
    Retorna la lista de solicitudes creadas.
    """
    alertas = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.studio_id == studio_id,
        AlertaVencimiento.resuelta_at == None,
    ).all()

    creadas = []
    for alerta in alertas:
        if not alerta.documentos_faltantes:
            continue

        for tipo_doc in alerta.documentos_faltantes:
            # Evitar duplicar solicitudes pendientes para el mismo vencimiento+tipo
            existente = db.query(SolicitudDocumentoAuto).filter(
                SolicitudDocumentoAuto.vencimiento_id == alerta.vencimiento_id,
                SolicitudDocumentoAuto.tipo_documento == tipo_doc,
                SolicitudDocumentoAuto.studio_id == studio_id,
                SolicitudDocumentoAuto.estado.in_([
                    EstadoSolicitud.pendiente, EstadoSolicitud.enviada
                ]),
            ).first()

            if existente:
                continue

            solicitud = SolicitudDocumentoAuto(
                studio_id=studio_id,
                cliente_id=alerta.cliente_id,
                vencimiento_id=alerta.vencimiento_id,
                tipo_documento=tipo_doc,
                estado=EstadoSolicitud.pendiente,
                canal="portal",
            )
            db.add(solicitud)
            creadas.append({
                "cliente_id": alerta.cliente_id,
                "vencimiento_id": alerta.vencimiento_id,
                "tipo_documento": tipo_doc,
            })

    db.commit()
    return creadas


def listar_solicitudes(db: Session, studio_id: int, cliente_id: int | None = None) -> list[SolicitudDocumentoAuto]:
    q = db.query(SolicitudDocumentoAuto).filter(SolicitudDocumentoAuto.studio_id == studio_id)
    if cliente_id is not None:
        q = q.filter(SolicitudDocumentoAuto.cliente_id == cliente_id)
    return q.order_by(SolicitudDocumentoAuto.created_at.desc()).all()


def marcar_enviada(db: Session, solicitud_id: int, studio_id: int, canal: str) -> SolicitudDocumentoAuto:
    solicitud = db.query(SolicitudDocumentoAuto).filter(
        SolicitudDocumentoAuto.id == solicitud_id,
        SolicitudDocumentoAuto.studio_id == studio_id,
    ).first()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    solicitud.estado = EstadoSolicitud.enviada
    solicitud.canal = canal
    solicitud.enviada_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(solicitud)
    return solicitud


def marcar_recibida(db: Session, solicitud_id: int, studio_id: int) -> SolicitudDocumentoAuto:
    solicitud = db.query(SolicitudDocumentoAuto).filter(
        SolicitudDocumentoAuto.id == solicitud_id,
        SolicitudDocumentoAuto.studio_id == studio_id,
    ).first()
    if not solicitud:
        raise HTTPException(status_code=404, detail="Solicitud no encontrada")

    solicitud.estado = EstadoSolicitud.recibida
    db.commit()
    db.refresh(solicitud)
    return solicitud
