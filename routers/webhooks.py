"""
Webhook de Telegram — recibe updates directamente de la Bot API.
No requiere autenticación JWT. La seguridad es por secretToken de Telegram
(header X-Telegram-Bot-Api-Secret-Token validado contra TELEGRAM_WEBHOOK_SECRET).
"""
import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database import get_db
from modules.asistente.adaptadores import telegram as tg
from modules.asistente.models import AsistenteCanal, AsistenteSesionWizard
from modules.asistente.schemas import MensajeEntrante
from modules.asistente import service

logger = logging.getLogger("pymeos")

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

_TELEGRAM_WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")

# ─── Definición de los wizards ────────────────────────────────────────────────

WIZARD_TASK_PASOS = [
    {"key": "titulo", "pregunta": "📝 <b>Crear tarea</b>\n\nPaso 1/5 — ¿Cuál es el título de la tarea?"},
    {"key": "tipo", "pregunta": (
        "Paso 2/5 — Elegí el tipo:\n"
        "1. declaracion\n2. conciliacion\n3. auditoria\n4. asesoramiento\n5. otro\n\n"
        "Respondé con el número o el nombre."
    )},
    {"key": "prioridad", "pregunta": (
        "Paso 3/5 — Elegí la prioridad:\n"
        "1. urgente\n2. alta\n3. normal\n4. baja\n\n"
        "Respondé con el número o el nombre."
    )},
    {"key": "fecha_limite", "pregunta": "Paso 4/5 — ¿Fecha límite? (formato DD/MM/AAAA o escribí <i>no</i> para omitir)"},
    {"key": "cliente_nombre", "pregunta": "Paso 5/5 — ¿Para qué cliente? Escribí el nombre o parte de él (o <i>no</i> para omitir)"},
]

WIZARD_CLIENTE_PASOS = [
    {"key": "nombre", "pregunta": "👤 <b>Nuevo cliente</b>\n\nPaso 1/6 — ¿Cuál es el nombre o razón social?"},
    {"key": "cuit_cuil", "pregunta": "Paso 2/6 — ¿CUIT/CUIL? (solo números, sin guiones)"},
    {"key": "condicion_fiscal", "pregunta": (
        "Paso 3/6 — Condición fiscal:\n"
        "1. responsable_inscripto\n2. monotributista\n3. exento\n4. no_responsable\n5. autonomos\n\n"
        "Respondé con el número o el nombre."
    )},
    {"key": "email", "pregunta": "Paso 4/6 — ¿Email? (o <i>no</i> para omitir)"},
    {"key": "telefono", "pregunta": "Paso 5/6 — ¿Teléfono? (o <i>no</i> para omitir)"},
    {"key": "honorarios_mensuales", "pregunta": "Paso 6/6 — ¿Honorarios mensuales en pesos? (número o <i>no</i>)"},
]

TIPO_TAREA_MAP = {"1": "declaracion", "2": "conciliacion", "3": "auditoria", "4": "asesoramiento", "5": "otro"}
PRIORIDAD_MAP = {"1": "urgente", "2": "alta", "3": "normal", "4": "baja"}
CONDICION_MAP = {
    "1": "responsable_inscripto",
    "2": "monotributista",
    "3": "exento",
    "4": "no_responsable",
    "5": "autonomos",
}


def _validar_telegram_request(request: Request) -> None:
    if not _TELEGRAM_WEBHOOK_SECRET:
        return
    header = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if header != _TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Unauthorized")


def _get_wizard(db: Session, telegram_user_id: str) -> AsistenteSesionWizard | None:
    return db.query(AsistenteSesionWizard).filter(
        AsistenteSesionWizard.telegram_user_id == telegram_user_id,
        AsistenteSesionWizard.expira_at >= datetime.utcnow(),
    ).first()


def _clear_wizard(db: Session, telegram_user_id: str) -> None:
    db.query(AsistenteSesionWizard).filter(
        AsistenteSesionWizard.telegram_user_id == telegram_user_id
    ).delete()
    db.commit()


def _start_wizard(db: Session, telegram_user_id: str, comando: str) -> AsistenteSesionWizard:
    _clear_wizard(db, telegram_user_id)
    wizard = AsistenteSesionWizard(
        telegram_user_id=telegram_user_id,
        comando=comando,
        paso_actual=0,
        datos_parciales={},
        expira_at=datetime.utcnow() + timedelta(minutes=15),
    )
    db.add(wizard)
    db.commit()
    db.refresh(wizard)
    return wizard


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    db: Session = Depends(get_db),
):
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
            bienvenida += (
                "Tu cuenta ya está vinculada. Comandos disponibles:\n\n"
                "/resumen — Resumen del día\n"
                "/vencimientos — Vencimientos próximos 7 días\n"
                "/task — Crear nueva tarea\n"
                "/cliente — Registrar nuevo cliente\n"
                "/cancelar — Cancelar operación en curso"
            )
        else:
            bienvenida += "Para vincular tu cuenta, pedile al administrador del estudio que te genere un código de vinculación."
        await tg.send_message(int(telegram_user_id), bienvenida)
        return {"ok": True}

    # Comando /vincular {codigo}
    if texto.startswith("/vincular "):
        await _handle_vincular(db, texto, telegram_user_id)
        return {"ok": True}

    # Comando /cancelar
    if texto.strip() in ("/cancelar", "/cancel"):
        wizard = _get_wizard(db, telegram_user_id)
        if wizard:
            _clear_wizard(db, telegram_user_id)
            await tg.send_message(int(telegram_user_id), "❌ Operación cancelada.")
        else:
            await tg.send_message(int(telegram_user_id), "No hay ninguna operación en curso.")
        return {"ok": True}

    # Comandos de wizard — requieren cuenta vinculada
    if texto.strip() in ("/task", "/tarea"):
        if not canal:
            await tg.send_message(int(telegram_user_id), "Tu cuenta no está vinculada. Usá /vincular para conectarla.")
            return {"ok": True}
        wizard = _start_wizard(db, telegram_user_id, "task")
        await tg.send_message(int(telegram_user_id), WIZARD_TASK_PASOS[0]["pregunta"])
        return {"ok": True}

    if texto.strip() == "/cliente":
        if not canal:
            await tg.send_message(int(telegram_user_id), "Tu cuenta no está vinculada. Usá /vincular para conectarla.")
            return {"ok": True}
        wizard = _start_wizard(db, telegram_user_id, "cliente")
        await tg.send_message(int(telegram_user_id), WIZARD_CLIENTE_PASOS[0]["pregunta"])
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

    # Verificar si hay un wizard activo
    wizard = _get_wizard(db, telegram_user_id)
    if wizard:
        if wizard.comando == "task":
            await _handle_wizard_task(db, wizard, texto, telegram_user_id)
        elif wizard.comando == "cliente":
            await _handle_wizard_cliente(db, wizard, texto, telegram_user_id)
        return {"ok": True}

    # Procesar mensaje normal con IA
    mensaje = MensajeEntrante(
        canal="telegram",
        tipo_usuario=canal.tipo_usuario,
        identificador_origen=telegram_user_id,
        contenido=texto,
    )
    await service.procesar_mensaje(db, mensaje)
    return {"ok": True}


# ─── Wizard /task ─────────────────────────────────────────────────────────────

async def _handle_wizard_task(
    db: Session, wizard: AsistenteSesionWizard, texto: str, telegram_user_id: str
) -> None:
    paso = wizard.paso_actual
    datos = dict(wizard.datos_parciales)
    t = texto.strip()

    try:
        if paso == 0:
            # título
            if not t:
                await tg.send_message(int(telegram_user_id), "El título no puede estar vacío.")
                return
            datos["titulo"] = t
            wizard.datos_parciales = datos
            wizard.paso_actual = 1
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_TASK_PASOS[1]["pregunta"])

        elif paso == 1:
            # tipo
            tipo = TIPO_TAREA_MAP.get(t, t.lower())
            opciones_validas = list(TIPO_TAREA_MAP.values())
            if tipo not in opciones_validas:
                await tg.send_message(int(telegram_user_id), f"Opción inválida. Elegí un número del 1 al 5 o el nombre exacto.")
                return
            datos["tipo"] = tipo
            wizard.datos_parciales = datos
            wizard.paso_actual = 2
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_TASK_PASOS[2]["pregunta"])

        elif paso == 2:
            # prioridad
            prioridad = PRIORIDAD_MAP.get(t, t.lower())
            opciones_validas = list(PRIORIDAD_MAP.values())
            if prioridad not in opciones_validas:
                await tg.send_message(int(telegram_user_id), "Opción inválida. Elegí un número del 1 al 4 o el nombre exacto.")
                return
            datos["prioridad"] = prioridad
            wizard.datos_parciales = datos
            wizard.paso_actual = 3
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_TASK_PASOS[3]["pregunta"])

        elif paso == 3:
            # fecha_limite
            if t.lower() not in ("no", "-", "omitir", ""):
                from datetime import date
                try:
                    partes = t.split("/")
                    if len(partes) == 3:
                        d, m, y = int(partes[0]), int(partes[1]), int(partes[2])
                        fecha = date(y, m, d)
                        datos["fecha_limite"] = fecha.isoformat()
                    else:
                        raise ValueError
                except (ValueError, IndexError):
                    await tg.send_message(int(telegram_user_id), "Formato inválido. Usá DD/MM/AAAA o escribí <i>no</i>.")
                    return
            wizard.datos_parciales = datos
            wizard.paso_actual = 4
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_TASK_PASOS[4]["pregunta"])

        elif paso == 4:
            # cliente_nombre — buscar en DB
            if t.lower() not in ("no", "-", "omitir", ""):
                from models.cliente import Cliente
                clientes = db.query(Cliente).filter(
                    Cliente.activo == True,
                    Cliente.nombre.ilike(f"%{t}%"),
                ).limit(5).all()

                if not clientes:
                    await tg.send_message(
                        int(telegram_user_id),
                        f"No encontré clientes con ese nombre. Escribí otro nombre o <i>no</i> para omitir."
                    )
                    return
                elif len(clientes) > 1:
                    opciones = "\n".join(f"{i+1}. {c.nombre}" for i, c in enumerate(clientes))
                    datos["_clientes_candidatos"] = [{"id": c.id, "nombre": c.nombre} for c in clientes]
                    wizard.datos_parciales = datos
                    wizard.paso_actual = 5  # paso extra: elegir de la lista
                    db.commit()
                    await tg.send_message(
                        int(telegram_user_id),
                        f"Encontré {len(clientes)} clientes. ¿Cuál es?\n{opciones}\n\nRespondé con el número."
                    )
                    return
                else:
                    datos["cliente_id"] = clientes[0].id
                    datos["cliente_nombre"] = clientes[0].nombre

            wizard.datos_parciales = datos
            wizard.paso_actual = 6  # confirmación
            db.commit()
            await _enviar_confirmacion_task(telegram_user_id, datos)

        elif paso == 5:
            # elegir cliente de la lista
            candidatos = datos.get("_clientes_candidatos", [])
            try:
                idx = int(t) - 1
                if idx < 0 or idx >= len(candidatos):
                    raise ValueError
            except ValueError:
                await tg.send_message(int(telegram_user_id), f"Elegí un número del 1 al {len(candidatos)}.")
                return
            datos["cliente_id"] = candidatos[idx]["id"]
            datos["cliente_nombre"] = candidatos[idx]["nombre"]
            datos.pop("_clientes_candidatos", None)
            wizard.datos_parciales = datos
            wizard.paso_actual = 6
            db.commit()
            await _enviar_confirmacion_task(telegram_user_id, datos)

        elif paso == 6:
            # confirmación
            if t.lower() in ("si", "sí", "s", "yes", "y", "ok", "confirmar"):
                await _crear_tarea_desde_wizard(db, datos, telegram_user_id)
                _clear_wizard(db, telegram_user_id)
            elif t.lower() in ("no", "n", "cancelar"):
                _clear_wizard(db, telegram_user_id)
                await tg.send_message(int(telegram_user_id), "❌ Tarea cancelada.")
            else:
                await tg.send_message(int(telegram_user_id), "Respondé <b>sí</b> para confirmar o <b>no</b> para cancelar.")

    except Exception as e:
        logger.error("Error en wizard task paso %d: %s", paso, e)
        _clear_wizard(db, telegram_user_id)
        await tg.send_message(int(telegram_user_id), "Ocurrió un error. La operación fue cancelada.")


async def _enviar_confirmacion_task(telegram_user_id: str, datos: dict) -> None:
    resumen = (
        "📋 <b>Confirmar nueva tarea</b>\n\n"
        f"<b>Título:</b> {datos.get('titulo', '—')}\n"
        f"<b>Tipo:</b> {datos.get('tipo', '—')}\n"
        f"<b>Prioridad:</b> {datos.get('prioridad', '—')}\n"
        f"<b>Fecha límite:</b> {datos.get('fecha_limite', 'Sin fecha')}\n"
        f"<b>Cliente:</b> {datos.get('cliente_nombre', 'Sin cliente')}\n\n"
        "¿Confirmás? Respondé <b>sí</b> o <b>no</b>."
    )
    await tg.send_message(int(telegram_user_id), resumen)


async def _crear_tarea_desde_wizard(db: Session, datos: dict, telegram_user_id: str) -> None:
    from schemas.tarea import TareaCreate
    from models.tarea import TipoTarea, PrioridadTarea
    from models.empleado import Empleado
    from services.tarea_service import crear_tarea

    # Obtener studio_id del empleado vinculado al canal de Telegram
    canal = db.query(AsistenteCanal).filter(
        AsistenteCanal.canal == "telegram",
        AsistenteCanal.identificador == telegram_user_id,
        AsistenteCanal.activo == True,
    ).first()
    empleado = db.query(Empleado).filter(Empleado.id == canal.usuario_id).first() if canal else None
    studio_id = empleado.studio_id if empleado else 1

    fecha_limite = None
    if datos.get("fecha_limite"):
        from datetime import date
        fecha_limite = date.fromisoformat(datos["fecha_limite"])

    tarea_data = TareaCreate(
        titulo=datos["titulo"],
        tipo=TipoTarea(datos.get("tipo", "otro")),
        prioridad=PrioridadTarea(datos.get("prioridad", "normal")),
        cliente_id=datos.get("cliente_id"),
        fecha_limite=fecha_limite,
    )
    tarea = crear_tarea(db, tarea_data, studio_id)
    await tg.send_message(
        int(telegram_user_id),
        f"✅ Tarea creada: <b>{tarea.titulo}</b>\n"
        f"ID #{tarea.id} · {tarea.prioridad.value if hasattr(tarea.prioridad, 'value') else tarea.prioridad}"
    )


# ─── Wizard /cliente ──────────────────────────────────────────────────────────

async def _handle_wizard_cliente(
    db: Session, wizard: AsistenteSesionWizard, texto: str, telegram_user_id: str
) -> None:
    paso = wizard.paso_actual
    datos = dict(wizard.datos_parciales)
    t = texto.strip()

    try:
        if paso == 0:
            # nombre
            if not t:
                await tg.send_message(int(telegram_user_id), "El nombre no puede estar vacío.")
                return
            datos["nombre"] = t
            wizard.datos_parciales = datos
            wizard.paso_actual = 1
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_CLIENTE_PASOS[1]["pregunta"])

        elif paso == 1:
            # cuit_cuil — limpiar guiones y puntos
            cuit = t.replace("-", "").replace(".", "").strip()
            if not cuit.isdigit() or len(cuit) < 10:
                await tg.send_message(int(telegram_user_id), "CUIT inválido. Ingresá solo los números (ej. 20123456789).")
                return
            datos["cuit_cuil"] = cuit
            wizard.datos_parciales = datos
            wizard.paso_actual = 2
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_CLIENTE_PASOS[2]["pregunta"])

        elif paso == 2:
            # condicion_fiscal
            condicion = CONDICION_MAP.get(t, t.lower().replace(" ", "_"))
            opciones_validas = list(CONDICION_MAP.values())
            if condicion not in opciones_validas:
                await tg.send_message(int(telegram_user_id), "Opción inválida. Elegí un número del 1 al 4.")
                return
            datos["condicion_fiscal"] = condicion
            wizard.datos_parciales = datos
            wizard.paso_actual = 3
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_CLIENTE_PASOS[3]["pregunta"])

        elif paso == 3:
            # email
            if t.lower() not in ("no", "-", "omitir", ""):
                if "@" not in t:
                    await tg.send_message(int(telegram_user_id), "Email inválido. Ingresá un email válido o escribí <i>no</i>.")
                    return
                datos["email"] = t
            wizard.datos_parciales = datos
            wizard.paso_actual = 4
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_CLIENTE_PASOS[4]["pregunta"])

        elif paso == 4:
            # telefono
            if t.lower() not in ("no", "-", "omitir", ""):
                datos["telefono"] = t
            wizard.datos_parciales = datos
            wizard.paso_actual = 5
            db.commit()
            await tg.send_message(int(telegram_user_id), WIZARD_CLIENTE_PASOS[5]["pregunta"])

        elif paso == 5:
            # honorarios_mensuales
            if t.lower() not in ("no", "-", "omitir", ""):
                try:
                    honorarios = float(t.replace(",", ".").replace("$", "").strip())
                    datos["honorarios_mensuales"] = honorarios
                except ValueError:
                    await tg.send_message(int(telegram_user_id), "Ingresá un número válido o escribí <i>no</i>.")
                    return
            wizard.datos_parciales = datos
            wizard.paso_actual = 6
            db.commit()
            await _enviar_confirmacion_cliente(telegram_user_id, datos)

        elif paso == 6:
            # confirmación
            if t.lower() in ("si", "sí", "s", "yes", "y", "ok", "confirmar"):
                await _crear_cliente_desde_wizard(db, datos, telegram_user_id)
                _clear_wizard(db, telegram_user_id)
            elif t.lower() in ("no", "n", "cancelar"):
                _clear_wizard(db, telegram_user_id)
                await tg.send_message(int(telegram_user_id), "❌ Operación cancelada.")
            else:
                await tg.send_message(int(telegram_user_id), "Respondé <b>sí</b> para confirmar o <b>no</b> para cancelar.")

    except Exception as e:
        logger.error("Error en wizard cliente paso %d: %s", paso, e)
        _clear_wizard(db, telegram_user_id)
        await tg.send_message(int(telegram_user_id), "Ocurrió un error. La operación fue cancelada.")


async def _enviar_confirmacion_cliente(telegram_user_id: str, datos: dict) -> None:
    resumen = (
        "👤 <b>Confirmar nuevo cliente</b>\n\n"
        f"<b>Nombre:</b> {datos.get('nombre', '—')}\n"
        f"<b>CUIT/CUIL:</b> {datos.get('cuit_cuil', '—')}\n"
        f"<b>Condición fiscal:</b> {datos.get('condicion_fiscal', '—')}\n"
        f"<b>Email:</b> {datos.get('email', 'No ingresado')}\n"
        f"<b>Teléfono:</b> {datos.get('telefono', 'No ingresado')}\n"
        f"<b>Honorarios:</b> {datos.get('honorarios_mensuales', 'No ingresado')}\n\n"
        "¿Confirmás? Respondé <b>sí</b> o <b>no</b>."
    )
    await tg.send_message(int(telegram_user_id), resumen)


async def _crear_cliente_desde_wizard(db: Session, datos: dict, telegram_user_id: str) -> None:
    from schemas.cliente import ClienteCreate
    from models.cliente import CondicionFiscal, TipoPersona
    from models.empleado import Empleado
    from services.cliente_service import crear_cliente

    # Obtener studio_id del empleado vinculado al canal
    canal = db.query(AsistenteCanal).filter(
        AsistenteCanal.canal == "telegram",
        AsistenteCanal.identificador == telegram_user_id,
        AsistenteCanal.activo == True,
    ).first()
    empleado = db.query(Empleado).filter(Empleado.id == canal.usuario_id).first() if canal else None
    studio_id = empleado.studio_id if empleado else 1

    cliente_data = ClienteCreate(
        tipo_persona=TipoPersona.fisica,
        nombre=datos["nombre"],
        cuit_cuil=datos["cuit_cuil"],
        condicion_fiscal=CondicionFiscal(datos["condicion_fiscal"]),
        email=datos.get("email"),
        telefono=datos.get("telefono"),
        honorarios_mensuales=datos.get("honorarios_mensuales"),
    )
    cliente = crear_cliente(db, cliente_data, studio_id)
    await tg.send_message(
        int(telegram_user_id),
        f"✅ Cliente registrado: <b>{cliente.nombre}</b>\n"
        f"ID #{cliente.id} · CUIT {cliente.cuit_cuil}"
    )


# ─── Handlers existentes ──────────────────────────────────────────────────────

async def _handle_resolve_alert(db: Session, callback_data: str, telegram_user_id: str) -> None:
    try:
        alerta_id = int(callback_data.replace("resolve_alert_", ""))
        from models.empleado import Empleado
        from services.alert_service import resolver_alerta

        canal = db.query(AsistenteCanal).filter(
            AsistenteCanal.canal == "telegram",
            AsistenteCanal.identificador == telegram_user_id,
            AsistenteCanal.activo == True,
        ).first()
        empleado = db.query(Empleado).filter(Empleado.id == canal.usuario_id).first() if canal else None
        studio_id = empleado.studio_id if empleado else 1

        resolver_alerta(db, alerta_id, studio_id)
        await tg.send_message(int(telegram_user_id), "✅ Alerta marcada como resuelta.")
    except Exception as e:
        logger.error("Error resolviendo alerta desde Telegram: %s", e)
        await tg.send_message(int(telegram_user_id), "No pude resolver la alerta. Intentá desde la plataforma.")


async def _handle_vincular(db: Session, texto: str, telegram_user_id: str) -> None:
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
                "Comandos disponibles:\n"
                "/resumen — Resumen del día\n"
                "/vencimientos — Próximos 7 días\n"
                "/task — Crear nueva tarea\n"
                "/cliente — Registrar nuevo cliente\n"
                "/cancelar — Cancelar operación en curso",
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
