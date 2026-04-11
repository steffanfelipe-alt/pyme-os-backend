"""
Helper para obtener un cliente Anthropic configurado.
Prioridad: variable de entorno ANTHROPIC_API_KEY → clave guardada en StudioConfig (DB).
"""
import os

import anthropic
from fastapi import HTTPException
from sqlalchemy.orm import Session


def get_anthropic_client(db: Session) -> anthropic.AsyncAnthropic:
    """
    Retorna un AsyncAnthropic con la API key activa.
    Primero busca ANTHROPIC_API_KEY en el entorno; si no está, la lee de StudioConfig.
    Lanza HTTP 400 si no hay clave configurada.
    """
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        from models.studio_config import StudioConfig
        cfg = db.query(StudioConfig).first()
        if cfg:
            key = (cfg.anthropic_api_key or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="Clave de Anthropic no configurada. Guardala en Configuración → API Keys.",
        )
    return anthropic.AsyncAnthropic(api_key=key)
