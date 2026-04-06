"""
Adaptador Telegram: normaliza payloads entrantes y envía mensajes salientes.
Usa httpx.AsyncClient para compatibilidad con FastAPI async.
"""
import logging
import os

import httpx

logger = logging.getLogger("pymeos")


def _api_base() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    return f"https://api.telegram.org/bot{token}"


async def send_message(chat_id: int | str, text: str, reply_markup: dict | None = None) -> bool:
    """Envía un mensaje de texto al chat indicado. Retorna True si tuvo éxito."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado, mensaje no enviado")
        return False
    try:
        payload: dict = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            payload["reply_markup"] = reply_markup
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{_api_base()}/sendMessage", json=payload)
            resp.raise_for_status()
        return True
    except Exception as e:
        logger.error("Error enviando mensaje Telegram a %s: %s", chat_id, e)
        return False


def extraer_telegram_user_id(update: dict) -> str | None:
    """Extrae el telegram_user_id del update entrante."""
    try:
        if "message" in update:
            return str(update["message"]["from"]["id"])
        if "callback_query" in update:
            return str(update["callback_query"]["from"]["id"])
    except (KeyError, TypeError):
        pass
    return None


def extraer_texto(update: dict) -> str | None:
    """Extrae el texto o callback_data del update."""
    try:
        if "message" in update:
            return update["message"].get("text")
        if "callback_query" in update:
            return update["callback_query"].get("data")
    except (KeyError, TypeError):
        pass
    return None


def extraer_callback_query_id(update: dict) -> str | None:
    """Extrae el callback_query_id para responder con answerCallbackQuery."""
    try:
        return update["callback_query"]["id"]
    except (KeyError, TypeError):
        return None


async def answer_callback_query(callback_query_id: str, text: str = "") -> None:
    """Responde a un callback query para quitar el spinner del botón."""
    if not os.environ.get("TELEGRAM_BOT_TOKEN") or not callback_query_id:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(
                f"{_api_base()}/answerCallbackQuery",
                json={"callback_query_id": callback_query_id, "text": text},
            )
    except Exception as e:
        logger.error("Error respondiendo callback query: %s", e)


def build_inline_keyboard(buttons: list[list[dict]]) -> dict:
    """Construye un InlineKeyboardMarkup desde una lista de listas de botones."""
    return {"inline_keyboard": buttons}
