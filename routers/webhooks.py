"""
Webhook de Telegram — recibe updates directamente de la Bot API.
No requiere autenticación JWT. La seguridad es por secretToken de Telegram
(header X-Telegram-Bot-Api-Secret-Token validado contra TELEGRAM_WEBHOOK_SECRET).
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from modules.asistente.adaptadores import telegram as tg
from modules.asistente.models import AsistenteCanal
from modules.asistente.schemas import MensajeEntrante
from modules.asistente import service

logger = logging.getLogger("pymeos")

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

_TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")


def _validar_telegram_request(request: Request) -> None:
    """Valida el header secret de Telegram si TELEGRAM_WEBHOOK_SECRET está configurado."""
    if not _TELEGRAM_WEBHOOK_SECRET:
        return
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if header != _TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Recibe updates de Telegram y los procesa.
    Valida el header X-Telegram-Bot-Api-Secret-Token si TELEGRAM_WEBHOOK_SECRET está configurado.
    """
    _validar_telegram_request(request)

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    telegram_user_id = tg.extraer_telegram_user_id(update)
    texto = tg.extraer_texto(update)
    callback_id = tg.extraer_callback_query_id(update)

    if not telegram_user_id:
        return {"ok": True}

    # Responder callbacks de botones
    if callback_id:
        await tg.answer_callback_query(callback_id)
        if texto and texto.startswith("resolve_alert_"):
            await _handle_resolve_alert(db, texto, telegram_user_id)
            return {"ok": True}

    if not texto:
        return {"ok": True}

    # Verificar si el usuario está registrado
    canal = db.query(AsistenteCanal).filter(
        AsistenteCanal.canal == "telegram",
        AsistenteCanal.identificador == telegram_user_id,
        AsistenteCanal.activo == True,
    ).first()

    # Comando /start
    if texto == "/start":
        bienvenida = (
            "👋 <b>Bienvenido al asistente del estudio.</b>\n\n"
            "Todas las conversaciones están cifradas por la infraestructura de seguridad de Telegram. "
            "Los datos del estudio son procesados de forma segura y privada.\n\n"
        )
        if canal:
            bienvenida += "Tu cuenta ya está vinculada. Podés hacer consultas sobre tus clientes y tareas."
        else:
            bienvenida += "Para vincular tu cuenta, pedile al administrador del estudio que te genere un código de vinculación."
        await tg.send_message(int(telegram_user_id), bienvenida)
        return {"ok": True}

    # Comando /vincular {codigo}
    if texto.startswith("/vincular "):
        await _handle_vincular(db, texto, telegram_user_id)
        return {"ok": True}

    # Comando /resumen
    if texto.strip() == "/resumen":
        await _handle_resumen(db, telegram_user_id, canal)
        return {"ok": True}

    # Comando /vencimientos
    if texto.strip() == "/vencimientos":
        await _handle_vencimientos(db, telegram_user_id, canal)
        return {"ok": True}

    # Si no está registrado
    if not canal:
        await tg.send_message(
            int(telegram_user_id),
            "Tu cuenta no está registrada. Contactá al administrador del estudio.",
        )
        return {"ok": True}

    # Procesar mensaje normal
    mensaje = MensajeEntrante(
        canal="telegram",
        tipo_usuario=canal.tipo_usuario,
        identificador_origen=telegram_user_id,
        contenido=texto,
    )
    await service.procesar_mensaje(db, mensaje)
    return {"ok": True}


async def _handle_resolve_alert(db: Session, callback_data: str, telegram_user_id: str) -> None:
    try:
        alerta_id = int(callback_data.replace("resolve_alert_", ""))
        from services.alert_service import resolver_alerta
        resolver_alerta(db, alerta_id)
        await tg.send_message(int(telegram_user_id), "✅ Alerta marcada como resuelta.")
    except Exception as e:
        logger.error("Error resolviendo alerta desde Telegram: %s", e)
        await tg.send_message(int(telegram_user_id), "No pude resolver la alerta. Intentá desde la plataforma.")


async def _handle_vincular(db: Session, texto: str, telegram_user_id: str) -> None:
    """Procesa el comando /vincular {codigo}."""
    try:
        partes = texto.split(" ", 1)
        if len(partes) < 2:
            await tg.send_message(int(telegram_user_id), "Formato: /vincular CODIGO")
            return

        codigo = partes[1].strip()

        from models.studio_config import StudioConfig
        config = db.query(StudioConfig).first()
        if not config:
            await tg.send_message(int(telegram_user_id), "No se encontró la configuración del estudio.")
            return

        if (
            not hasattr(config, "telegram_connect_code")
            or config.telegram_connect_code != codigo
            or (config.telegram_connect_expires_at and config.telegram_connect_expires_at < datetime.now(timezone.utc))
        ):
            await tg.send_message(int(telegram_user_id), "Código incorrecto o expirado.")
            return

        config.telegram_chat_id = int(telegram_user_id)
        config.telegram_active = True
        db.commit()

        from models.empleado import Empleado, RolEmpleado
        dueno = db.query(Empleado).filter(
            Empleado.rol == RolEmpleado.dueno,
            Empleado.activo == True,
        ).first()

        if dueno:
            canal_existente = db.query(AsistenteCanal).filter(
                AsistenteCanal.canal == "telegram",
                AsistenteCanal.usuario_id == dueno.id,
                AsistenteCanal.tipo_usuario == "empleado",
            ).first()
            if canal_existente:
                canal_existente.identificador = telegram_user_id
                canal_existente.activo = True
            else:
                db.add(AsistenteCanal(
                    tipo_usuario="empleado",
                    usuario_id=dueno.id,
                    canal="telegram",
                    identificador=telegram_user_id,
                    activo=True,
                ))
            db.commit()
            await tg.send_message(
                int(telegram_user_id),
                f"✅ Bot vinculado correctamente. Hola, <b>{dueno.nombre}</b>.\n\n"
                "Ya podés hacerme consultas sobre clientes, tareas y vencimientos.",
            )
        else:
            await tg.send_message(
                int(telegram_user_id),
                "✅ Bot vinculado al estudio. Pero no encontré un empleado con rol dueño "
                "para registrar el canal. Pedile al administrador que te registre manualmente.",
            )

    except Exception as e:
        logger.error("Error en /vincular: %s", e)
        await tg.send_message(int(telegram_user_id), "Error al vincular. Intentá de nuevo.")


async def _handle_resumen(db: Session, telegram_user_id: str, canal) -> None:
    """Comando /resumen — envía el resumen diario on-demand."""
    if not canal:
        await tg.send_message(int(telegram_user_id), "Tu cuenta no está vinculada.")
        return
    try:
        from models.empleado import Empleado
        from modules.asistente import contexto as ctx
        from modules.asistente import notificador

        empleado = db.query(Empleado).filter(Empleado.id == canal.usuario_id).first()
        if not empleado:
            await tg.send_message(int(telegram_user_id), "No se encontró tu usuario.")
            return

        rol = empleado.rol.value if hasattr(empleado.rol, "value") else str(empleado.rol)
        datos = ctx.contexto_dueno(db) if rol == "dueno" else ctx.contexto_contador(db, canal.usuario_id)

        venc_proximos = datos.get("vencimientos_proximos", [])
        resumen = {
            "vence_hoy": [v for v in venc_proximos if v.get("dias_restantes", 99) <= 0],
            "proximos_3_dias": [v for v in venc_proximos if 1 <= v.get("dias_restantes", 99) <= 3],
            "tareas_activas": datos.get("tareas_activas", []),
            "documentos_pendientes": datos.get("documentos_pendientes_revision", 0),
        }

        await notificador.enviar_resumen_diario_telegram(
            chat_id=int(telegram_user_id),
            nombre_empleado=empleado.nombre,
            resumen=resumen,
        )
    except Exception as e:
        logger.error("Error en /resumen: %s", e)
        await tg.send_message(int(telegram_user_id), "No pude generar el resumen. Intentá de nuevo.")


async def _handle_vencimientos(db: Session, telegram_user_id: str, canal) -> None:
    """Comando /vencimientos — lista los próximos 7 días."""
    if not canal:
        await tg.send_message(int(telegram_user_id), "Tu cuenta no está vinculada.")
        return
    try:
        from datetime import date, timedelta
        from models.vencimiento import Vencimiento, EstadoVencimiento
        from models.cliente import Cliente

        hoy = date.today()
        proximos_7 = hoy + timedelta(days=7)

        vencimientos = (
            db.query(Vencimiento, Cliente)
            .join(Cliente, Vencimiento.cliente_id == Cliente.id)
            .filter(
                Vencimiento.estado == EstadoVencimiento.pendiente,
                Vencimiento.fecha_vencimiento >= hoy,
                Vencimiento.fecha_vencimiento <= proximos_7,
                Cliente.activo == True,
            )
            .order_by(Vencimiento.fecha_vencimiento)
            .limit(15)
            .all()
        )

        if not vencimientos:
            await tg.send_message(int(telegram_user_id), "📅 No hay vencimientos pendientes en los próximos 7 días.")
            return

        lineas = ["📅 <b>Vencimientos próximos 7 días:</b>\n"]
        for v, c in vencimientos:
            dias = (v.fecha_vencimiento - hoy).days
            tipo = v.tipo.value if hasattr(v.tipo, "value") else str(v.tipo)
            icono = "🔴" if dias <= 1 else ("⚠️" if dias <= 3 else "📋")
            lineas.append(f"{icono} {tipo} — {c.nombre} ({v.fecha_vencimiento.strftime('%d/%m')} — {dias}d)")

        await tg.send_message(int(telegram_user_id), "\n".join(lineas))

    except Exception as e:
        logger.error("Error en /vencimientos: %s", e)
        await tg.send_message(int(telegram_user_id), "No pude listar los vencimientos. Intentá de nuevo.")
