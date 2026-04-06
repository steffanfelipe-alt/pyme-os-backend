"""
Servicio de integración con Gmail API.
Maneja OAuth2, watch de Pub/Sub, descarga de emails y envío de respuestas.
Los tokens se encriptan con Fernet antes de persistir.
"""
import base64
import logging
import os
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any

from cryptography.fernet import Fernet
from fastapi import HTTPException
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from models.gmail_config import GmailConfig

logger = logging.getLogger("pymeos")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

# Cuerpo HTML máximo: 50 KB
_MAX_HTML_BYTES = 50 * 1024


def _fernet() -> Fernet:
    """Instancia Fernet usando FERNET_KEY del entorno."""
    key = os.environ.get("FERNET_KEY", "")
    if not key:
        raise RuntimeError("FERNET_KEY no está configurada en .env")
    return Fernet(key.encode() if isinstance(key, str) else key)


def _encrypt(texto: str) -> str:
    return _fernet().encrypt(texto.encode()).decode()


def _decrypt(cifrado: str) -> str:
    return _fernet().decrypt(cifrado.encode()).decode()


# ---------------------------------------------------------------------------
# OAuth2
# ---------------------------------------------------------------------------

def obtener_url_oauth(redirect_uri: str) -> str:
    """Genera la URL de autorización OAuth2 de Google."""
    client_secrets = os.environ.get("GOOGLE_CLIENT_SECRETS_FILE", "client_secrets.json")
    flow = Flow.from_client_secrets_file(client_secrets, scopes=SCOPES, redirect_uri=redirect_uri)
    url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    return url


def completar_oauth(code: str, redirect_uri: str, studio_email: str, db: Session) -> GmailConfig:
    """
    Intercambia el código de autorización por tokens y guarda (encriptados) en DB.
    """
    client_secrets = os.environ.get("GOOGLE_CLIENT_SECRETS_FILE", "client_secrets.json")
    flow = Flow.from_client_secrets_file(client_secrets, scopes=SCOPES, redirect_uri=redirect_uri)
    flow.fetch_token(code=code)
    creds = flow.credentials

    config = db.query(GmailConfig).filter(GmailConfig.studio_email == studio_email).first()
    if not config:
        config = GmailConfig(studio_email=studio_email, gmail_address=creds.token_uri or "")

    config.access_token_enc = _encrypt(creds.token)
    config.refresh_token_enc = _encrypt(creds.refresh_token)
    config.token_expiry = creds.expiry
    config.gmail_address = studio_email
    config.activo = True

    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def _get_credentials(config: GmailConfig) -> Credentials:
    """Reconstruye Credentials y refresca el access_token si expiró."""
    creds = Credentials(
        token=_decrypt(config.access_token_enc),
        refresh_token=_decrypt(config.refresh_token_enc),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.environ.get("GOOGLE_CLIENT_ID", ""),
        client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        scopes=SCOPES,
    )
    if creds.expired:
        creds.refresh(Request())
        config.access_token_enc = _encrypt(creds.token)
        config.token_expiry = creds.expiry

    return creds


# ---------------------------------------------------------------------------
# Watch de Pub/Sub
# ---------------------------------------------------------------------------

def configurar_watch(config: GmailConfig, db: Session) -> None:
    """Registra (o renueva) el watch de Gmail para recibir notificaciones vía Pub/Sub."""
    creds = _get_credentials(config)
    service = build("gmail", "v1", credentials=creds)

    topic = os.environ.get("GMAIL_PUBSUB_TOPIC", "")
    if not topic:
        raise RuntimeError("GMAIL_PUBSUB_TOPIC no está configurada en .env")

    resp = service.users().watch(
        userId="me",
        body={"labelIds": ["INBOX"], "topicName": topic},
    ).execute()

    config.watch_history_id = str(resp.get("historyId", ""))
    # El watch expira en 7 días; renovamos con margen de 1 día
    config.watch_expiry = datetime.now(timezone.utc) + timedelta(days=7)
    db.commit()
    logger.info("Gmail watch renovado. Expira: %s", config.watch_expiry)


def job_renovar_gmail_watch(db: Session) -> None:
    """Job APScheduler: renueva todos los watches activos antes de que expiren."""
    configs = db.query(GmailConfig).filter(GmailConfig.activo == True).all()
    ahora = datetime.now(timezone.utc)
    for cfg in configs:
        if cfg.watch_expiry is None or (cfg.watch_expiry - ahora) < timedelta(days=2):
            try:
                configurar_watch(cfg, db)
            except Exception as exc:
                logger.error("Error renovando watch para %s: %s", cfg.gmail_address, exc)


# ---------------------------------------------------------------------------
# Descarga de emails
# ---------------------------------------------------------------------------

def descargar_email(gmail_message_id: str, config: GmailConfig) -> dict[str, Any]:
    """
    Descarga un email de Gmail y extrae sus campos relevantes.
    El HTML se trunca a 50 KB.
    """
    creds = _get_credentials(config)
    service = build("gmail", "v1", credentials=creds)

    msg = service.users().messages().get(
        userId="me",
        id=gmail_message_id,
        format="full",
    ).execute()

    payload = msg.get("payload", {})
    headers = {h["name"].lower(): h["value"] for h in payload.get("headers", [])}

    remitente = headers.get("from", "")
    asunto = headers.get("subject", "")
    fecha_str = headers.get("date", "")

    cuerpo_texto, cuerpo_html = _extraer_cuerpo(payload)
    tiene_adjuntos = any(
        p.get("filename") for p in _listar_partes(payload)
        if p.get("filename")
    )

    # Truncar HTML si supera el límite
    if cuerpo_html and len(cuerpo_html.encode()) > _MAX_HTML_BYTES:
        cuerpo_html = cuerpo_html.encode()[:_MAX_HTML_BYTES].decode(errors="ignore")
        logger.warning("HTML truncado para gmail_message_id=%s", gmail_message_id)

    return {
        "gmail_message_id": gmail_message_id,
        "remitente": remitente,
        "asunto": asunto,
        "cuerpo_texto": cuerpo_texto,
        "cuerpo_html": cuerpo_html,
        "tiene_adjuntos": tiene_adjuntos,
        "fecha_recibido": _parsear_fecha(fecha_str),
    }


def _listar_partes(payload: dict) -> list[dict]:
    partes = []
    if "parts" in payload:
        for parte in payload["parts"]:
            partes.extend(_listar_partes(parte))
    else:
        partes.append(payload)
    return partes


def _extraer_cuerpo(payload: dict) -> tuple[str | None, str | None]:
    texto, html = None, None
    for parte in _listar_partes(payload):
        mime = parte.get("mimeType", "")
        data = parte.get("body", {}).get("data", "")
        if not data:
            continue
        contenido = base64.urlsafe_b64decode(data + "==").decode(errors="ignore")
        if mime == "text/plain" and not texto:
            texto = contenido
        elif mime == "text/html" and not html:
            html = contenido
    return texto, html


def _parsear_fecha(fecha_str: str) -> datetime:
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(fecha_str).replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


# ---------------------------------------------------------------------------
# Envío de respuestas
# ---------------------------------------------------------------------------

def enviar_respuesta(
    destinatario: str,
    asunto: str,
    cuerpo: str,
    thread_id: str | None,
    config: GmailConfig,
) -> None:
    """Envía un email de respuesta usando la cuenta Gmail del estudio."""
    creds = _get_credentials(config)
    service = build("gmail", "v1", credentials=creds)

    msg = MIMEText(cuerpo, "plain", "utf-8")
    msg["to"] = destinatario
    msg["subject"] = f"Re: {asunto}" if not asunto.startswith("Re:") else asunto
    msg["from"] = config.gmail_address

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    body: dict[str, Any] = {"raw": raw}
    if thread_id:
        body["threadId"] = thread_id

    service.users().messages().send(userId="me", body=body).execute()
    logger.info("Respuesta enviada a %s", destinatario)
