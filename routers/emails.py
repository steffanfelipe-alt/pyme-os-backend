"""
Router de emails entrantes.
Dependencias de autenticación: RBAC según spec.
"""
import base64
import json
import logging
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import require_rol, solo_dueno
from database import get_db
from models.cliente import Cliente
from models.email_entrante import EmailEntrante
from models.gmail_config import GmailConfig

logger = logging.getLogger("pymeos")

router = APIRouter(prefix="/api/emails", tags=["Emails"])

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EmailResumen(BaseModel):
    id: int
    remitente: str
    asunto: Optional[str]
    categoria: Optional[str]
    urgencia: Optional[str]
    resumen: Optional[str]
    estado: str
    requiere_respuesta: bool
    requiere_revision_manual: bool
    motivo_revision: Optional[str]
    tiene_adjuntos: bool
    asignado_a: Optional[int]
    cliente_id: Optional[int]
    fecha_recibido: datetime

    class Config:
        from_attributes = True


class EmailDetalle(EmailResumen):
    cuerpo_texto: Optional[str]
    borrador_respuesta: Optional[str]
    borrador_editado: Optional[str]
    borrador_aprobado: bool
    respuesta_enviada_at: Optional[datetime]
    leido_at: Optional[datetime]

    class Config:
        from_attributes = True


class EditarRespuestaRequest(BaseModel):
    texto: str


class AsignarRequest(BaseModel):
    empleado_id: Optional[int]


class CambiarCategoriaRequest(BaseModel):
    categoria: str


# ---------------------------------------------------------------------------
# Bandeja de entrada
# ---------------------------------------------------------------------------


@router.get("", response_model=list[EmailResumen])
def listar_emails(
    estado: Optional[str] = None,
    categoria: Optional[str] = None,
    pendiente_aprobacion: bool = False,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo", "rrhh")),
):
    """Lista emails del usuario según su rol. Máximo 200 por página."""
    limit = min(limit, 200)
    query = db.query(EmailEntrante)
    rol = current_user.get("rol")

    if rol == "contador":
        query = query.filter(EmailEntrante.asignado_a == current_user.get("empleado_id"))
    elif rol == "rrhh":
        query = query.filter(
            EmailEntrante.categoria.in_(["postulacion_laboral", "solicitud_licencia", "consulta_interna"])
        )
    elif rol == "administrativo":
        query = query.filter(EmailEntrante.urgencia.in_(["media", "baja"]))
    # dueno: sin filtro adicional

    # Filtro especial: emails con borrador IA pendiente de aprobación
    if pendiente_aprobacion:
        query = query.filter(
            EmailEntrante.requiere_respuesta == True,
            EmailEntrante.borrador_aprobado == False,
            EmailEntrante.estado != "respondido",
        )
    elif estado:
        query = query.filter(EmailEntrante.estado == estado)

    if categoria:
        query = query.filter(EmailEntrante.categoria == categoria)

    return query.order_by(EmailEntrante.fecha_recibido.desc()).offset(skip).limit(limit).all()


@router.get("/{email_id}", response_model=EmailDetalle)
def obtener_email(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo", "rrhh")),
):
    """Retorna el detalle y marca como leído."""
    email = _get_email_o_404(email_id, db)
    if email.estado == "no_leido":
        email.estado = "leido"
        email.leido_at = datetime.utcnow()
        db.commit()
    return email


@router.patch("/{email_id}/asignar")
def asignar_email(
    email_id: int,
    body: AsignarRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
):
    email = _get_email_o_404(email_id, db)
    email.asignado_a = body.empleado_id
    db.commit()
    return {"ok": True}


@router.patch("/{email_id}/archivar")
def archivar_email(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo", "rrhh")),
):
    email = _get_email_o_404(email_id, db)
    email.estado = "archivado"
    db.commit()
    return {"ok": True}


@router.patch("/{email_id}/categoria")
def cambiar_categoria(
    email_id: int,
    body: CambiarCategoriaRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Cambia manualmente la categoría de un email (routing manual)."""
    CATEGORIAS_VALIDAS = {
        "documento_recibido", "consulta_fiscal", "postulacion_laboral",
        "solicitud_licencia", "consulta_interna", "proveedor",
        "notificacion_afip", "urgente", "propuesta_comercial",
        "reclamo", "spam", "otro",
    }
    if body.categoria not in CATEGORIAS_VALIDAS:
        raise HTTPException(status_code=400, detail=f"Categoría inválida. Válidas: {', '.join(CATEGORIAS_VALIDAS)}")
    email = _get_email_o_404(email_id, db)
    email.categoria = body.categoria
    db.commit()
    return {"ok": True}


@router.patch("/{email_id}/marcar-spam")
def marcar_spam(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "administrativo")),
):
    email = _get_email_o_404(email_id, db)
    email.estado = "spam"
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------------------


@router.post("/{email_id}/aprobar-respuesta")
def aprobar_respuesta(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Aprueba y envía el borrador generado por la IA."""
    email = _get_email_o_404(email_id, db)

    if not email.requiere_respuesta or not email.borrador_respuesta:
        raise HTTPException(status_code=400, detail="Este email no tiene borrador pendiente")

    if email.requiere_revision_manual:
        raise HTTPException(
            status_code=400,
            detail=f"Requiere revisión manual antes de enviar. Motivo: {email.motivo_revision}",
        )

    _enviar_respuesta_via_gmail(email, email.borrador_respuesta, db)
    email.borrador_aprobado = True
    email.estado = "respondido"
    email.respuesta_enviada_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/{email_id}/editar-respuesta")
def editar_y_enviar_respuesta(
    email_id: int,
    body: EditarRespuestaRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Guarda el borrador editado y lo envía. Disponible incluso si requiere_revision_manual=True."""
    email = _get_email_o_404(email_id, db)

    if not body.texto.strip():
        raise HTTPException(status_code=400, detail="El texto de la respuesta no puede estar vacío")

    email.borrador_editado = body.texto
    _enviar_respuesta_via_gmail(email, body.texto, db)
    email.borrador_aprobado = True
    email.requiere_revision_manual = False  # El humano revisó y aprobó
    email.estado = "respondido"
    email.respuesta_enviada_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.post("/{email_id}/responder")
def respuesta_manual(
    email_id: int,
    body: EditarRespuestaRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador", "administrativo")),
):
    """Respuesta manual sin usar el borrador de la IA."""
    email = _get_email_o_404(email_id, db)

    _enviar_respuesta_via_gmail(email, body.texto, db)
    email.estado = "respondido"
    email.respuesta_enviada_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Configuración Gmail
# ---------------------------------------------------------------------------


@router.get("/config/estado")
def estado_gmail(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    config = db.query(GmailConfig).filter(GmailConfig.activo == True).first()
    if not config:
        return {"conectado": False}
    return {
        "conectado": True,
        "gmail_address": config.gmail_address,
        "watch_expiry": config.watch_expiry,
    }


@router.post("/config/conectar")
def iniciar_oauth(
    redirect_uri: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Genera la URL de autorización OAuth2 de Google."""
    from services.gmail_service import obtener_url_oauth
    url = obtener_url_oauth(redirect_uri)
    return {"auth_url": url}


@router.post("/config/callback")
def oauth_callback(
    code: str,
    redirect_uri: str,
    studio_email: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Intercambia el código OAuth2 y guarda la config."""
    from services.gmail_service import completar_oauth, configurar_watch
    config = completar_oauth(code, redirect_uri, studio_email, db)
    configurar_watch(config, db)
    return {"ok": True, "gmail_address": config.gmail_address}


@router.post("/config/webhook")
async def webhook_gmail(request: Request, db: Session = Depends(get_db)):
    """
    Endpoint que recibe notificaciones de Gmail via Google Pub/Sub.
    No requiere JWT — valida el token de Google en el header.
    """
    # Validar que la request viene de Google Pub/Sub
    _validar_pubsub_request(request)

    body = await request.json()
    message = body.get("message", {})
    data_b64 = message.get("data", "")

    if not data_b64:
        return {"ok": True}

    data = json.loads(base64.b64decode(data_b64).decode())
    email_address = data.get("emailAddress")
    history_id = data.get("historyId")

    if not email_address or not history_id:
        return {"ok": True}

    config = (
        db.query(GmailConfig)
        .filter(GmailConfig.gmail_address == email_address, GmailConfig.activo == True)
        .first()
    )
    if not config:
        logger.warning("Webhook recibido para gmail no configurado: %s", email_address)
        return {"ok": True}

    # Procesar en background — descargar y clasificar emails nuevos
    try:
        await _procesar_nuevos_emails(config, history_id, db)
    except Exception as exc:
        logger.error("Error procesando webhook Gmail: %s", exc)

    return {"ok": True}


@router.delete("/config")
def desconectar_gmail(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    config = db.query(GmailConfig).filter(GmailConfig.activo == True).first()
    if config:
        config.activo = False
        db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _get_email_o_404(email_id: int, db: Session) -> EmailEntrante:
    email = db.query(EmailEntrante).filter(EmailEntrante.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email no encontrado")
    return email


def _enviar_respuesta_via_gmail(email: EmailEntrante, texto: str, db: Session) -> None:
    """Envía la respuesta si hay Gmail configurado. En dev/tests sin config es no-op."""
    config = db.query(GmailConfig).filter(GmailConfig.activo == True).first()
    if not config:
        logger.warning("Sin Gmail configurado — respuesta no enviada por email")
        return
    from services.gmail_service import enviar_respuesta
    enviar_respuesta(
        destinatario=email.remitente,
        asunto=email.asunto or "",
        cuerpo=texto,
        thread_id=None,
        config=config,
    )


def _validar_pubsub_request(request: Request) -> None:
    """Valida que la request venga de Google Pub/Sub verificando el bearer token."""
    auth_header = request.headers.get("Authorization", "")
    pubsub_token = os.environ.get("PUBSUB_VERIFICATION_TOKEN", "")

    if pubsub_token and not auth_header.endswith(pubsub_token):
        raise HTTPException(status_code=403, detail="Token de Pub/Sub inválido")


async def _procesar_nuevos_emails(config: GmailConfig, history_id: str, db: Session) -> None:
    """Descarga emails nuevos desde historyId y los procesa."""
    from services.gmail_service import descargar_email
    from services.email_clasificador import clasificar_email
    from services.email_router_service import procesar_email_entrante

    from services.gmail_service import _get_credentials
    from googleapiclient.discovery import build

    creds = _get_credentials(config)
    service = build("gmail", "v1", credentials=creds)

    # Obtener historial desde el último historyId conocido
    start_id = config.watch_history_id or history_id
    result = service.users().history().list(
        userId="me",
        startHistoryId=start_id,
        historyTypes=["messageAdded"],
    ).execute()

    message_ids = []
    for record in result.get("history", []):
        for added in record.get("messagesAdded", []):
            msg_id = added.get("message", {}).get("id")
            if msg_id:
                message_ids.append(msg_id)

    # Obtener clientes registrados para el clasificador
    clientes = db.query(Cliente).filter(Cliente.activo == True).all()
    lista_clientes = [{"nombre": c.nombre, "cuit_cuil": c.cuit_cuil} for c in clientes]

    for msg_id in message_ids:
        # Evitar duplicados
        existente = db.query(EmailEntrante).filter(EmailEntrante.gmail_message_id == msg_id).first()
        if existente:
            continue

        try:
            datos = descargar_email(msg_id, config)
        except Exception as exc:
            logger.error("Error descargando email %s: %s", msg_id, exc)
            continue

        email = EmailEntrante(
            remitente=datos["remitente"],
            asunto=datos["asunto"],
            cuerpo_texto=datos["cuerpo_texto"],
            cuerpo_html=datos["cuerpo_html"],
            tiene_adjuntos=datos["tiene_adjuntos"],
            fecha_recibido=datos["fecha_recibido"],
            gmail_message_id=datos["gmail_message_id"],
            estado="no_leido",
        )
        db.add(email)
        db.flush()

        try:
            clasificacion = await clasificar_email(
                remitente=datos["remitente"],
                asunto=datos["asunto"] or "",
                cuerpo=datos["cuerpo_texto"] or "",
                clientes_registrados=lista_clientes,
                db=db,
            )
            procesar_email_entrante(email, clasificacion, db)
        except Exception as exc:
            logger.error("Error clasificando email %s: %s", msg_id, exc)

        # Procesar adjuntos si el email es de tipo documento_recibido y hay cliente vinculado
        if (
            email.cliente_id is not None
            and email.categoria == "documento_recibido"
            and datos.get("tiene_adjuntos")
        ):
            from services.documento_service import procesar_adjunto_email
            for adjunto in datos.get("adjuntos_metadata", []):
                try:
                    doc = await procesar_adjunto_email(
                        db=db,
                        cliente_id=email.cliente_id,
                        gmail_message_id=msg_id,
                        adjunto=adjunto,
                        service=service,
                    )
                    if doc:
                        logger.info(
                            "Adjunto clasificado — doc_id=%d email=%s cliente=%d",
                            doc.id, msg_id, email.cliente_id,
                        )
                except Exception as exc:
                    logger.error(
                        "Error procesando adjunto %s del email %s: %s",
                        adjunto.get("filename"), msg_id, exc,
                    )

    config.watch_history_id = history_id
    db.commit()


# ---------------------------------------------------------------------------
# Email reminder a clientes (generado por Claude)
# ---------------------------------------------------------------------------


class ClientReminderRequest(BaseModel):
    cliente_id: int
    asunto_hint: Optional[str] = None


@router.post("/clients/reminder")
async def enviar_reminder_cliente(
    body: ClientReminderRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_rol("dueno", "contador")),
):
    """
    Genera un email profesional a un cliente con contenido creado por Claude API.
    El contador no puede enviar sin que Claude genere el contenido.
    """
    import anthropic
    from models.email_log import EmailLog

    cliente = db.query(Cliente).filter(
        Cliente.id == body.cliente_id, Cliente.activo == True
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    email_dest = cliente.email_notificaciones or cliente.email
    if not email_dest:
        raise HTTPException(status_code=422, detail="El cliente no tiene email configurado")

    # Obtener documentos pendientes del período
    from models.vencimiento import Vencimiento, EstadoVencimiento
    from datetime import date, timedelta
    hoy = date.today()
    proximos = (
        db.query(Vencimiento)
        .filter(
            Vencimiento.cliente_id == cliente.id,
            Vencimiento.estado == EstadoVencimiento.pendiente,
            Vencimiento.fecha_vencimiento <= hoy + timedelta(days=30),
        )
        .all()
    )
    venc_texto = "\n".join(
        f"- {v.tipo.value}: vence {v.fecha_vencimiento.strftime('%d/%m/%Y')}"
        for v in proximos
    ) if proximos else "Sin vencimientos próximos."

    nombre_estudio = os.environ.get("STUDIO_NAME", "el estudio")
    prompt = (
        f"Generá un email profesional y amigable de un estudio contable ({nombre_estudio}) "
        f"a su cliente {cliente.nombre} (CUIT {cliente.cuit_cuil}).\n"
        f"El email debe recordarle sobre documentación pendiente y/o vencimientos próximos.\n"
        f"Vencimientos del cliente:\n{venc_texto}\n"
        f"{'Tema sugerido: ' + body.asunto_hint if body.asunto_hint else ''}\n\n"
        f"Devolvé SOLO un JSON con: {{\"asunto\": str, \"cuerpo\": str}}\n"
        f"El cuerpo debe estar en texto plano (no HTML). Usá vos/usted según corresponda."
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        import json as _json
        datos = _json.loads(raw)
    except Exception as e:
        logger.error("Error generando email con Claude: %s", e)
        raise HTTPException(status_code=502, detail="No se pudo generar el contenido del email")

    asunto = datos.get("asunto", f"Recordatorio — {nombre_estudio}")
    cuerpo = datos.get("cuerpo", "")

    # Enviar por SMTP
    from modules.asistente.adaptadores.email import send_email
    enviado = send_email(email_dest, asunto, cuerpo, nombre_estudio)

    # Registrar en email_log
    log = EmailLog(
        studio_id=current_user.get("studio_id"),
        recipient_type="client",
        recipient_email=email_dest,
        email_type="reminder",
        subject=asunto,
        status="sent" if enviado else "failed",
        error_message=None if enviado else "SMTP send failed",
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    return {
        "id": log.id,
        "asunto": asunto,
        "cuerpo": cuerpo,
        "enviado": enviado,
        "destinatario": email_dest,
    }
