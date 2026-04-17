"""Configuración Sección 11 — Sistema (solo dueno)."""
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import get_studio_id, solo_dueno
from database import get_db
from models.studio import Studio
from models.studio_config import StudioConfig

router = APIRouter(prefix="/config/sistema", tags=["Config - Sistema"])


class SistemaUpdate(BaseModel):
    claude_api_key: Optional[str] = None
    claude_modelo: Optional[str] = None
    debug_mode: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_puerto: Optional[int] = None
    smtp_usuario: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_usar_tls: Optional[bool] = None
    email_notificaciones: Optional[str] = None


def _mask(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 4:
        return "••••"
    return "••••" + value[-4:]


def _get_studio(db: Session, studio_id: int) -> Studio:
    s = db.query(Studio).filter(Studio.id == studio_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Studio no encontrado")
    return s


@router.get("/estado")
def estado_sistema(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Estado de todos los componentes críticos del sistema."""
    s = _get_studio(db, studio_id)
    config = db.query(StudioConfig).first()

    # Claude API
    claude_key = s.claude_api_key_encrypted or (config.anthropic_api_key if config else None) or os.getenv("ANTHROPIC_API_KEY")
    claude_ok = bool(claude_key)

    # AFIP
    afip_ok = bool(s.afip_certificado_path and s.afip_clave_privada_path and s.afip_punto_venta)

    # Email
    email_ok = bool(s.smtp_host and s.smtp_usuario) or bool(os.getenv("SMTP_HOST"))

    # Telegram
    tg_ok = bool(s.telegram_configurado)
    if not tg_ok and config:
        tg_ok = bool(config.telegram_active and config.telegram_chat_id)

    return {
        "claude_api": {"ok": claude_ok, "estado": "conectado" if claude_ok else "sin_configurar"},
        "afip": {"ok": afip_ok, "estado": "configurado" if afip_ok else "sin_configurar"},
        "email_smtp": {"ok": email_ok, "estado": "configurado" if email_ok else "sin_configurar"},
        "telegram": {"ok": tg_ok, "estado": "conectado" if tg_ok else "sin_conectar"},
        "portal_cliente": {"ok": s.portal_habilitado, "estado": "activo" if s.portal_habilitado else "desactivado"},
        "base_datos": {"ok": True, "estado": "ok"},
        # Configuración actual
        "claude_modelo": s.claude_modelo,
        "claude_api_key_masked": _mask(s.claude_api_key_encrypted),
        "debug_mode": s.debug_mode,
        "afip_modo": s.afip_modo,
    }


@router.patch("")
def actualizar_sistema(
    data: SistemaUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    s = _get_studio(db, studio_id)
    if data.claude_api_key is not None:
        s.claude_api_key_encrypted = data.claude_api_key  # En producción: cifrar con Fernet
    if data.claude_modelo is not None:
        s.claude_modelo = data.claude_modelo
    if data.debug_mode is not None:
        s.debug_mode = data.debug_mode
    if data.smtp_host is not None:
        s.smtp_host = data.smtp_host
    if data.smtp_puerto is not None:
        s.smtp_puerto = data.smtp_puerto
    if data.smtp_usuario is not None:
        s.smtp_usuario = data.smtp_usuario
    if data.smtp_password is not None:
        s.smtp_password_encrypted = data.smtp_password  # En producción: cifrar
    if data.smtp_usar_tls is not None:
        s.smtp_usar_tls = data.smtp_usar_tls
    if data.email_notificaciones is not None:
        s.email_notificaciones = data.email_notificaciones
    db.commit()
    return {"ok": True}


@router.post("/test-claude")
async def test_claude(
    db: Session = Depends(get_db),
    current_user: dict = Depends(solo_dueno),
    studio_id: int = Depends(get_studio_id),
):
    """Llamada de prueba a la Claude API."""
    s = _get_studio(db, studio_id)
    api_key = s.claude_api_key_encrypted or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"ok": False, "mensaje": "API key no configurada"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=s.claude_modelo or "claude-sonnet-4-6",
            max_tokens=10,
            messages=[{"role": "user", "content": "ping"}],
        )
        return {"ok": True, "mensaje": "Claude API responde correctamente"}
    except Exception as e:
        return {"ok": False, "mensaje": str(e)}
