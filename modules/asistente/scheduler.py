"""
Jobs proactivos del módulo Asistente.
Diseñados para registrarse en el APScheduler de main.py.
"""
import asyncio
import logging
from datetime import date, timedelta

logger = logging.getLogger("pymeos")


def job_resumen_diario_empleados() -> None:
    """Envía el resumen diario a todos los empleados con canal Telegram activo."""
    try:
        from database import SessionLocal
        from models.empleado import Empleado
        from modules.asistente import contexto as ctx
        from modules.asistente.models import AsistenteCanal
        from modules.asistente import notificador

        hoy = date.today()

        with SessionLocal() as db:
            canales = db.query(AsistenteCanal).filter(
                AsistenteCanal.canal == "telegram",
                AsistenteCanal.tipo_usuario == "empleado",
                AsistenteCanal.activo == True,
            ).all()

            for canal in canales:
                try:
                    empleado = db.query(Empleado).filter(Empleado.id == canal.usuario_id).first()
                    if not empleado:
                        continue

                    rol = empleado.rol.value if hasattr(empleado.rol, "value") else str(empleado.rol)
                    if rol == "dueno":
                        datos = ctx.contexto_dueno(db)
                    else:
                        datos = ctx.contexto_contador(db, canal.usuario_id)

                    venc_proximos = datos.get("vencimientos_proximos", [])
                    vence_hoy = [v for v in venc_proximos if v.get("dias_restantes", 99) <= 0]
                    proximos_3 = [v for v in venc_proximos if 1 <= v.get("dias_restantes", 99) <= 3]

                    resumen = {
                        "vence_hoy": vence_hoy,
                        "proximos_3_dias": proximos_3,
                        "tareas_activas": datos.get("tareas_activas", []),
                        "documentos_pendientes": datos.get("documentos_pendientes_revision", 0),
                    }

                    # notificador.enviar_resumen_diario_telegram is async
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(notificador.enviar_resumen_diario_telegram(
                            chat_id=int(canal.identificador),
                            nombre_empleado=empleado.nombre,
                            resumen=resumen,
                        ))
                    except RuntimeError:
                        asyncio.run(notificador.enviar_resumen_diario_telegram(
                            chat_id=int(canal.identificador),
                            nombre_empleado=empleado.nombre,
                            resumen=resumen,
                        ))
                except Exception as e:
                    logger.error("Error enviando resumen diario a empleado id=%d: %s", canal.usuario_id, e)

        logger.info("Job resumen diario asistente completado — %d canales procesados", len(canales))
    except Exception as e:
        logger.error("Error en job resumen diario asistente: %s", e)
