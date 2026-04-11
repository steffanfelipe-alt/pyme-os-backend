"""
Gestión de API Keys, tokens e integraciones del estudio.
Las claves sensibles nunca se devuelven en texto plano —
solo se muestra si están configuradas y los últimos 4 chars.
"""
import os
import random
import string
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import solo_dueno
from database import get_db
from models.studio_config import StudioConfig

router = APIRouter(prefix="/api/configuracion", tags=["Configuracion"])


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


def _get_or_create_config(db: Session) -> StudioConfig:
    config = db.query(StudioConfig).first()
    if not config:
        config = StudioConfig()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ApiKeysResponse(BaseModel):
    telegram_bot_token: str | None = None
    telegram_webhook_url: str | None = None
    anthropic_api_key: str | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    # Flags de variables de entorno configuradas (informativo)
    telegram_bot_token_env: bool = False
    anthropic_api_key_env: bool = False


class ApiKeysUpdate(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_webhook_url: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_from: Optional[str] = None


def _build_response(config: StudioConfig) -> ApiKeysResponse:
    return ApiKeysResponse(
        telegram_bot_token=_mask(config.telegram_bot_token),
        telegram_webhook_url=config.telegram_webhook_url,
        anthropic_api_key=_mask(config.anthropic_api_key),
        smtp_host=config.smtp_host,
        smtp_port=config.smtp_port,
        smtp_user=config.smtp_user,
        smtp_password=_mask(config.smtp_password),
        smtp_from=config.smtp_from,
        telegram_bot_token_env=bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        anthropic_api_key_env=bool(os.environ.get("ANTHROPIC_API_KEY")),
    )


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/api-keys", response_model=ApiKeysResponse)
def get_api_keys(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    return _build_response(_get_or_create_config(db))


@router.put("/api-keys", response_model=ApiKeysResponse)
def update_api_keys(
    data: ApiKeysUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    config = _get_or_create_config(db)

    if data.telegram_bot_token is not None and data.telegram_bot_token.strip():
        config.telegram_bot_token = data.telegram_bot_token.strip()
    if data.telegram_webhook_url is not None:
        url = data.telegram_webhook_url.strip()
        if url and not url.startswith("https://"):
            raise HTTPException(status_code=400, detail="La URL del webhook debe comenzar con https://")
        config.telegram_webhook_url = url or None
    if data.anthropic_api_key is not None and data.anthropic_api_key.strip():
        config.anthropic_api_key = data.anthropic_api_key.strip()
    if data.smtp_host is not None:
        config.smtp_host = data.smtp_host.strip() or None
    if data.smtp_port is not None:
        config.smtp_port = data.smtp_port
    if data.smtp_user is not None:
        config.smtp_user = data.smtp_user.strip() or None
    if data.smtp_password is not None and data.smtp_password.strip():
        config.smtp_password = data.smtp_password.strip()
    if data.smtp_from is not None:
        config.smtp_from = data.smtp_from.strip() or None

    db.commit()
    db.refresh(config)
    return _build_response(config)


@router.post("/telegram/set-webhook")
def registrar_webhook_telegram(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Lee el token y la URL guardados en config y registra el webhook en Telegram."""
    config = _get_or_create_config(db)

    token = config.telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise HTTPException(status_code=400, detail="Token de Telegram no configurado.")

    webhook_url = (config.telegram_webhook_url or "").rstrip("/")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="URL del webhook no configurada.")

    full_url = f"{webhook_url}/webhooks/telegram"

    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": full_url},
            timeout=10,
        )
        result = r.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error conectando a Telegram: {e}")

    if not result.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"Telegram rechazó el webhook: {result.get('description', 'Error desconocido')}",
        )

    return {"ok": True, "webhook_url": full_url, "descripcion": result.get("description")}


@router.get("/telegram/webhook-info")
def info_webhook_telegram(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Consulta el estado actual del webhook registrado en Telegram."""
    config = _get_or_create_config(db)
    token = config.telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise HTTPException(status_code=400, detail="Token de Telegram no configurado.")
    try:
        r = httpx.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=10)
        info = r.json().get("result", {})
        return {
            "url": info.get("url", ""),
            "pending_updates": info.get("pending_update_count", 0),
            "last_error": info.get("last_error_message"),
        }
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error consultando Telegram: {e}")


@router.post("/telegram/generar-codigo")
def generar_codigo_vinculacion_telegram(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """
    Genera un código de vinculación de 6 caracteres válido por 15 minutos.
    El usuario debe enviarlo al bot como: /vincular CODIGO
    """
    config = _get_or_create_config(db)

    codigo = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    expira_en = datetime.utcnow() + timedelta(minutes=15)

    config.telegram_connect_code = codigo
    config.telegram_connect_expires_at = expira_en
    db.commit()

    return {
        "codigo": codigo,
        "expira_en": expira_en.isoformat(),
        "instrucciones": f"Enviá al bot de Telegram: /vincular {codigo}",
    }


@router.get("/telegram/estado")
def estado_telegram(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
):
    """Devuelve el estado actual de la integración Telegram del estudio."""
    config = _get_or_create_config(db)
    return {
        "telegram_active": config.telegram_active or False,
        "telegram_chat_id_configurado": config.telegram_chat_id is not None,
        "webhook_url_configurada": bool(config.telegram_webhook_url),
        "token_configurado": bool(config.telegram_bot_token or os.environ.get("TELEGRAM_BOT_TOKEN")),
        "codigo_pendiente": bool(
            config.telegram_connect_code
            and config.telegram_connect_expires_at
            and config.telegram_connect_expires_at > datetime.utcnow()
        ),
    }
