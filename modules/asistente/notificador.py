"""
Envía mensajes salientes al usuario por su canal configurado.
"""
import logging
import os
from datetime import date

from sqlalchemy.orm import Session

from modules.asistente.adaptadores import email as email_adapter
from modules.asistente.adaptadores import telegram as tg

logger = logging.getLogger("pymeos")


async def enviar_respuesta(canal: str, identificador: str, texto: str, reply_markup: dict | None = None) -> bool:
    """Envía la respuesta al usuario según su canal."""
    if canal == "telegram":
        return await tg.send_message(int(identificador), texto, reply_markup)
    if canal == "email":
        asunto = f"Re: consulta al estudio — {date.today().strftime('%d/%m/%Y')}"
        nombre_estudio = os.environ.get("STUDIO_NAME", "")
        return email_adapter.send_email(identificador, asunto, texto, nombre_estudio)
    logger.warning("Canal desconocido para envío: %s", canal)
    return False


async def enviar_alerta_vencimiento_telegram(chat_id: int, cliente_nombre: str, tipo_obligacion: str,
                                        fecha: str, dias_restantes: int, alerta_id: int) -> bool:
    """Formatea y envía una alerta de vencimiento por Telegram."""
    icono = "🔴" if dias_restantes <= 1 else ("⚠️" if dias_restantes <= 3 else "📅")
    texto = (
        f"{icono} <b>Vencimiento próximo</b>\n"
        f"Cliente: {cliente_nombre}\n"
        f"Obligación: {tipo_obligacion}\n"
        f"Vence: {fecha} ({dias_restantes} días)\n"
    )
    keyboard = tg.build_inline_keyboard([
        [
            {"text": "✅ Ya está gestionada", "callback_data": f"resolve_alert_{alerta_id}"},
            {"text": "📋 Ver plataforma", "callback_data": f"view_client_{alerta_id}"},
        ]
    ])
    return await tg.send_message(chat_id, texto, keyboard)


async def enviar_resumen_diario_telegram(chat_id: int, nombre_empleado: str, resumen: dict) -> bool:
    """Envía el resumen diario al empleado por Telegram."""
    hoy = date.today().strftime("%d/%m/%Y")
    vence_hoy = resumen.get("vence_hoy", [])
    proximos = resumen.get("proximos_3_dias", [])
    tareas = resumen.get("tareas_activas", [])
    docs = resumen.get("documentos_pendientes", 0)

    lineas = [f"📋 <b>Buenos días, {nombre_empleado}. Tu día de hoy — {hoy}:</b>"]

    if vence_hoy:
        lineas.append("\n🔴 <b>VENCE HOY</b>")
        for v in vence_hoy[:3]:
            lineas.append(f"• {v['tipo']} — {v['cliente']}")

    if proximos:
        lineas.append("\n⚠️ <b>PRÓXIMOS (3 días)</b>")
        for v in proximos[:3]:
            lineas.append(f"• {v['tipo']} — {v['cliente']} ({v['dias_restantes']}d)")

    if tareas:
        lineas.append("\n📝 <b>TAREAS ASIGNADAS</b>")
        for t in tareas[:3]:
            lineas.append(f"• {t['descripcion'][:50]}")

    if docs > 0:
        lineas.append(f"\n📎 <b>Documentos para revisar:</b> {docs}")

    texto = "\n".join(lineas)
    return await tg.send_message(chat_id, texto)
