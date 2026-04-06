"""
Servicio del Chatbot Interno de Consultas — experto en contabilidad argentina.
NO accede a datos del estudio. Solo contesta consultas de normativa fiscal.
"""
import logging
import os
import re

from sqlalchemy.orm import Session

from models.assistant_conversation import AssistantConversation

logger = logging.getLogger("pymeos")

_FALLBACK_RESPONSE = {
    "response": "No pude procesar tu consulta en este momento. Intentá de nuevo.",
    "disclaimer": None,
}

# Patrones que activan el disclaimer
_PATRON_FECHAS = re.compile(
    r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b"
    r"|vencimiento|vence|fecha límite"
    r"|\$\s?\d"
    r"|monto|importe|alícuota\s+\d",
    re.IGNORECASE,
)


def _necesita_disclaimer(texto: str) -> bool:
    """Detecta si la respuesta menciona fechas o montos específicos."""
    return bool(_PATRON_FECHAS.search(texto))


async def chat(
    db: Session,
    studio_id: int | None,
    user_id: int | None,
    message: str,
    conversation_history: list[dict],
    session_id: str,
) -> dict:
    """Procesa una consulta de contabilidad AR y retorna la respuesta."""
    try:
        import anthropic
        from prompts.assistant_contable import DISCLAIMER_TEXT, SYSTEM_PROMPT

        messages = []
        for msg in conversation_history[-20:]:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )
        assistant_text = response.content[0].text.strip()

        has_disclaimer = _necesita_disclaimer(assistant_text) or _necesita_disclaimer(message)
        disclaimer = DISCLAIMER_TEXT if has_disclaimer else None

        _guardar_mensajes(db, studio_id, user_id, session_id, message, assistant_text, has_disclaimer)

        return {
            "response": assistant_text,
            "disclaimer": disclaimer,
        }

    except Exception as e:
        logger.error("Error en assistant chat: %s", e)
        _guardar_mensajes(db, studio_id, user_id, session_id, message,
                          _FALLBACK_RESPONSE["response"], False)
        return _FALLBACK_RESPONSE


def _guardar_mensajes(
    db: Session,
    studio_id: int | None,
    user_id: int | None,
    session_id: str,
    user_message: str,
    assistant_message: str,
    has_disclaimer: bool,
) -> None:
    try:
        db.add(AssistantConversation(
            studio_id=studio_id,
            user_id=user_id,
            session_id=session_id,
            role="user",
            content=user_message,
            has_disclaimer=False,
        ))
        db.add(AssistantConversation(
            studio_id=studio_id,
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=assistant_message,
            has_disclaimer=has_disclaimer,
        ))
        db.commit()
    except Exception as e:
        logger.error("Error guardando conversación assistant: %s", e)
