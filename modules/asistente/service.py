"""
Orquestador principal del módulo Asistente.
Resuelve usuario → construye contexto → interpreta → ejecuta → responde.
La desambiguación ocurre ANTES de llamar a Claude.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models.cliente import Cliente
from models.empleado import Empleado
from modules.asistente import contexto as ctx
from modules.asistente import interprete
from modules.asistente import notificador
from modules.asistente.models import (
    AsistenteCanal,
    AsistenteConfirmacionPendiente,
    AsistenteMensaje,
)
from modules.asistente.schemas import MensajeEntrante, MensajeProcesado

logger = logging.getLogger("pymeos")


def _registrar_mensaje(
    db: Session,
    studio_id: int | None,
    tipo_usuario: str,
    usuario_id: int,
    canal: str,
    contenido_raw: str,
    contenido_procesado: str,
    intencion: str | None = None,
    entidades: dict | None = None,
    estado: str = "procesado",
    error_detalle: str | None = None,
) -> None:
    try:
        db.add(AsistenteMensaje(
            studio_id=studio_id,
            tipo_usuario=tipo_usuario,
            usuario_id=usuario_id,
            canal=canal,
            direccion="entrante",
            contenido_raw=contenido_raw,
            contenido_procesado=contenido_procesado,
            intencion_detectada=intencion,
            entidades_extraidas=entidades,
            estado=estado,
            error_detalle=error_detalle,
        ))
        db.commit()
    except Exception as e:
        logger.error("Error registrando mensaje en DB: %s", e)


def _resolver_canal(db: Session, canal: str, identificador: str) -> AsistenteCanal | None:
    """Busca el canal activo para el identificador dado."""
    return db.query(AsistenteCanal).filter(
        AsistenteCanal.canal == canal,
        AsistenteCanal.identificador == identificador,
        AsistenteCanal.activo == True,
    ).first()


def _buscar_coincidencias_cliente(db: Session, nombre: str, empleado_id: int | None) -> list[Cliente]:
    """Busca clientes activos cuyo nombre contenga el texto dado."""
    query = db.query(Cliente).filter(
        Cliente.activo == True,
        Cliente.nombre.ilike(f"%{nombre}%"),
    )
    if empleado_id:
        query = query.filter(Cliente.contador_asignado_id == empleado_id)
    return query.limit(5).all()


async def procesar_mensaje(db: Session, mensaje: MensajeEntrante) -> MensajeProcesado:
    """
    Punto de entrada principal: procesa un mensaje entrante y retorna la respuesta.
    """
    canal = _resolver_canal(db, mensaje.canal, mensaje.identificador_origen)

    if not canal:
        await _responder_no_registrado(mensaje)
        return MensajeProcesado(
            usuario_id=0,
            tipo_usuario=mensaje.tipo_usuario,
            intencion="no_registrado",
            respuesta="Tu cuenta no está registrada. Contactá al administrador del estudio.",
            requiere_confirmacion=False,
        )

    usuario_id = canal.usuario_id
    studio_id = canal.studio_id

    # Construir contexto según perfil
    if mensaje.tipo_usuario == "empleado":
        empleado = db.query(Empleado).filter(Empleado.id == usuario_id).first()
        if not empleado:
            return MensajeProcesado(
                usuario_id=usuario_id,
                tipo_usuario="empleado",
                intencion="error",
                respuesta="No encontré tu perfil de empleado. Contactá al administrador.",
                requiere_confirmacion=False,
            )

        rol = empleado.rol.value if hasattr(empleado.rol, "value") else str(empleado.rol)
        if rol == "dueno":
            datos_ctx = ctx.contexto_dueno(db)
        else:
            datos_ctx = ctx.contexto_contador(db, usuario_id)

        # Desambiguación: si el mensaje menciona un nombre → verificar coincidencias antes de Claude
        # (Claude recibe la lista de coincidencias en el contexto si hay ambigüedad)
        resultado = await interprete.interpretar_empleado(
            mensaje=mensaje.contenido,
            contexto_datos=datos_ctx,
            nombre_empleado=empleado.nombre,
            rol=rol,
        )

        # Si Claude detectó ambigüedad y hay un nombre mencionado, validar en DB
        if resultado.get("ambiguedad") and resultado.get("entidades", {}).get("nombre_mencionado"):
            nombre_mencionado = resultado["entidades"]["nombre_mencionado"]
            coincidencias = _buscar_coincidencias_cliente(db, nombre_mencionado, usuario_id if rol != "dueno" else None)
            if len(coincidencias) > 1:
                opciones = "\n".join(
                    f"{i+1}. {c.nombre} — CUIT {c.cuit_cuil}"
                    for i, c in enumerate(coincidencias)
                )
                respuesta = f"Encontré {len(coincidencias)} clientes con ese nombre. ¿A cuál te referís?\n{opciones}\n\nRespondé con el número o el CUIT."
                _registrar_mensaje(db, studio_id, "empleado", usuario_id, mensaje.canal,
                                   mensaje.contenido, respuesta, "desambiguacion", resultado.get("entidades"))
                await notificador.enviar_respuesta(mensaje.canal, mensaje.identificador_origen, respuesta)
                return MensajeProcesado(
                    usuario_id=usuario_id,
                    tipo_usuario="empleado",
                    intencion="desambiguacion",
                    respuesta=respuesta,
                    requiere_confirmacion=False,
                )

        respuesta = resultado.get("respuesta", "No pude procesar tu mensaje.")
        requiere_confirmacion = resultado.get("requiere_confirmacion", False)
        confirmacion_id = None

        if requiere_confirmacion and resultado.get("operacion_a_confirmar"):
            conf = AsistenteConfirmacionPendiente(
                usuario_id=usuario_id,
                canal=mensaje.canal,
                operacion=resultado["operacion_a_confirmar"],
                expira_at=datetime.utcnow() + timedelta(minutes=5),
                confirmado=None,
            )
            db.add(conf)
            db.commit()
            db.refresh(conf)
            confirmacion_id = conf.id

        _registrar_mensaje(
            db, studio_id, "empleado", usuario_id, mensaje.canal,
            mensaje.contenido, respuesta,
            resultado.get("intencion"), resultado.get("entidades"),
            estado="requiere_confirmacion" if requiere_confirmacion else "procesado",
        )
        await notificador.enviar_respuesta(mensaje.canal, mensaje.identificador_origen, respuesta)

        return MensajeProcesado(
            usuario_id=usuario_id,
            tipo_usuario="empleado",
            intencion=resultado.get("intencion", "desconocida"),
            respuesta=respuesta,
            requiere_confirmacion=requiere_confirmacion,
            confirmacion_id=confirmacion_id,
        )

    else:  # cliente
        import os
        datos_ctx = ctx.contexto_cliente(db, usuario_id)
        resultado = await interprete.interpretar_cliente(
            mensaje=mensaje.contenido,
            contexto_datos=datos_ctx,
            nombre_estudio=os.environ.get("STUDIO_NAME", "el estudio"),
        )
        email_resp = resultado.get("respuesta_email", {})
        respuesta = email_resp.get("cuerpo", "Recibimos tu mensaje. Te responderemos a la brevedad.")
        asunto = email_resp.get("asunto", "Re: su consulta")

        _registrar_mensaje(db, studio_id, "cliente", usuario_id, mensaje.canal,
                           mensaje.contenido, respuesta, resultado.get("intencion"))

        from modules.asistente.adaptadores.email import send_email
        import os
        send_email(
            to=mensaje.identificador_origen,
            subject=asunto,
            body_text=respuesta,
            nombre_estudio=os.environ.get("STUDIO_NAME", ""),
        )

        return MensajeProcesado(
            usuario_id=usuario_id,
            tipo_usuario="cliente",
            intencion=resultado.get("intencion", "desconocida"),
            respuesta=respuesta,
            requiere_confirmacion=False,
        )


async def _responder_no_registrado(mensaje: MensajeEntrante) -> None:
    """Envía respuesta a usuarios no registrados."""
    texto = "Tu cuenta no está registrada en el sistema. Contactá al administrador del estudio."
    await notificador.enviar_respuesta(mensaje.canal, mensaje.identificador_origen, texto)


def procesar_confirmacion(db: Session, confirmacion_id: int, confirmado: bool) -> dict:
    """Procesa la confirmación o cancelación de una operación pendiente."""
    conf = db.query(AsistenteConfirmacionPendiente).filter(
        AsistenteConfirmacionPendiente.id == confirmacion_id,
        AsistenteConfirmacionPendiente.confirmado == None,
        AsistenteConfirmacionPendiente.expira_at >= datetime.utcnow(),
    ).first()

    if not conf:
        return {"error": "Confirmación no encontrada o expirada"}

    conf.confirmado = confirmado
    db.commit()

    if not confirmado:
        return {"resultado": "Operación cancelada"}

    # Etapa D: solo lectura. Las operaciones de escritura se implementan en Etapa E.
    return {"resultado": "Confirmación registrada. La operación se ejecutará en breve."}
