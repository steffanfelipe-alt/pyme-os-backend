import logging
import os
import smtplib
from collections import defaultdict
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from database import SessionLocal
from models.cliente import Cliente
from models.empleado import Empleado
from models.studio_config import StudioConfig
from models.vencimiento import EstadoVencimiento, Vencimiento
from services import alert_service

logger = logging.getLogger("pymeos")

_UMBRAL_DIAS_DEFAULT = 7

MAIL_FROM = os.environ.get("MAIL_FROM", "")
MAIL_TO_FALLBACK = os.environ.get("MAIL_TO", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def _construir_cuerpo(destinatario_nombre: str, vencimientos: list[dict]) -> str:
    hoy = date.today()
    lineas = [
        f"<h2>Hola {destinatario_nombre}, estos son tus vencimientos próximos — {hoy.strftime('%d/%m/%Y')}</h2>",
        "<table border='1' cellpadding='6' cellspacing='0'>",
        "<tr><th>Cliente</th><th>CUIT</th><th>Tipo</th><th>Descripción</th><th>Vence</th><th>Días</th></tr>",
    ]
    for v in vencimientos:
        dias = (v["fecha_vencimiento"] - hoy).days
        color = "#ff4444" if dias < 0 else ("#ffaa00" if dias <= 3 else "#000000")
        lineas.append(
            f"<tr>"
            f"<td>{v['cliente_nombre']}</td>"
            f"<td>{v['cuit_cuil']}</td>"
            f"<td>{v['tipo']}</td>"
            f"<td>{v['descripcion']}</td>"
            f"<td>{v['fecha_vencimiento'].strftime('%d/%m/%Y')}</td>"
            f"<td style='color:{color}'><b>{dias}</b></td>"
            f"</tr>"
        )
    lineas.append("</table>")
    return "\n".join(lineas)


def _enviar_email(destinatario_email: str, asunto: str, cuerpo_html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = MAIL_FROM
    msg["To"] = destinatario_email
    msg.attach(MIMEText(cuerpo_html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.sendmail(MAIL_FROM, destinatario_email, msg.as_string())


def enviar_email_notificacion(destinatario: str, asunto: str, cuerpo: str) -> None:
    """Wrapper público para envío de emails de notificación (usado por alert_service)."""
    _enviar_email(destinatario, asunto, cuerpo)


def job_notificaciones_vencimientos() -> None:
    """Job diario: agrupa vencimientos por contador asignado y envía un email a cada uno."""
    logger.info("Job notificaciones — iniciando")

    db: Session = SessionLocal()
    try:
        hoy = date.today()

        # Leer umbral desde DB; fallback al valor por defecto si no hay config
        studio_config = db.query(StudioConfig).first()
        umbral_dias = (
            studio_config.umbral_dias_notificacion
            if studio_config is not None
            else _UMBRAL_DIAS_DEFAULT
        )
        limite = hoy + timedelta(days=umbral_dias)

        # Auto-marcar vencidos (global, afecta todos los estudios intencionalmente)
        db.query(Vencimiento).filter(
            Vencimiento.estado == EstadoVencimiento.pendiente,
            Vencimiento.fecha_vencimiento < hoy,
        ).update({"estado": EstadoVencimiento.vencido})
        db.commit()

        # Actualizar alertas por estudio — generar_alertas requiere studio_id
        try:
            from models.studio import Studio
            studios = db.query(Studio).all()
            for studio in studios:
                alert_service.generar_alertas(db, studio.id)
            logger.info("Job notificaciones — alertas actualizadas para %d estudios", len(studios))
        except Exception as e:
            logger.error("Job notificaciones — error al generar alertas: %s", e)

        # Envío de emails — solo si SMTP está configurado
        if not all([MAIL_FROM, MAIL_TO_FALLBACK, SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
            logger.warning("Job notificaciones — variables SMTP no configuradas, emails omitidos")
            return

        # Buscar vencimientos próximos + vencidos con datos del cliente
        # Filtro por studio_id evita mezclar datos entre estudios
        rows = (
            db.query(Vencimiento, Cliente)
            .join(Cliente, Vencimiento.cliente_id == Cliente.id)
            .filter(
                Vencimiento.estado.in_([EstadoVencimiento.pendiente, EstadoVencimiento.vencido]),
                Vencimiento.fecha_vencimiento <= limite,
                Cliente.activo == True,
                Vencimiento.studio_id == Cliente.studio_id,
            )
            .order_by(Vencimiento.fecha_vencimiento)
            .all()
        )

        if not rows:
            logger.info("Job notificaciones — sin vencimientos próximos, emails no enviados")
            return

        logger.info("Job notificaciones — %d vencimientos encontrados", len(rows))

        # Agrupar por contador asignado (None = sin contador → fallback)
        grupos: dict = defaultdict(list)
        for venc, cliente in rows:
            grupos[cliente.contador_asignado_id].append({
                "cliente_nombre": cliente.nombre,
                "cuit_cuil": cliente.cuit_cuil,
                "tipo": venc.tipo.value,
                "descripcion": venc.descripcion,
                "fecha_vencimiento": venc.fecha_vencimiento,
            })

        emails_enviados = 0
        for contador_id, vencimientos in grupos.items():
            # Determinar destinatario
            if contador_id is not None:
                empleado = db.query(Empleado).filter(Empleado.id == contador_id).first()
                if empleado and empleado.email:
                    destinatario_email = empleado.email
                    destinatario_nombre = empleado.nombre
                else:
                    destinatario_email = MAIL_TO_FALLBACK
                    destinatario_nombre = "equipo"
            else:
                destinatario_email = MAIL_TO_FALLBACK
                destinatario_nombre = "equipo"

            asunto = f"PyME OS — {len(vencimientos)} vencimientos próximos ({hoy.strftime('%d/%m/%Y')})"
            cuerpo = _construir_cuerpo(destinatario_nombre, vencimientos)

            try:
                _enviar_email(destinatario_email, asunto, cuerpo)
                logger.info(
                    "Job notificaciones — email enviado a %s (%d vencimientos)",
                    destinatario_email,
                    len(vencimientos),
                )
                emails_enviados += 1
            except Exception as e:
                logger.error(
                    "Job notificaciones — error enviando a %s: %s",
                    destinatario_email,
                    e,
                )

        logger.info("Job notificaciones — finalizado, %d emails enviados", emails_enviados)

    except Exception as e:
        logger.error("Job notificaciones — error general: %s", e)
    finally:
        db.close()


def job_resumen_semanal_email() -> None:
    """Job semanal (lunes 8:00 AM AR): envía resumen consolidado al dueño del estudio."""
    logger.info("Job resumen semanal — iniciando")

    db: Session = SessionLocal()
    try:
        from models.empleado import RolEmpleado
        from models.alerta import AlertaVencimiento

        # Buscar dueño del estudio
        dueno = db.query(Empleado).filter(
            Empleado.rol == RolEmpleado.dueno,
            Empleado.activo == True,
        ).first()
        if not dueno or not dueno.email:
            logger.warning("Job resumen semanal — no hay dueño con email configurado")
            return

        if not all([MAIL_FROM, SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
            logger.warning("Job resumen semanal — SMTP no configurado")
            return

        hoy = date.today()
        fin_semana = hoy + timedelta(days=7)

        # Vencimientos de la semana
        vencimientos_semana = (
            db.query(Vencimiento, Cliente)
            .join(Cliente, Vencimiento.cliente_id == Cliente.id)
            .filter(
                Vencimiento.estado == EstadoVencimiento.pendiente,
                Vencimiento.fecha_vencimiento >= hoy,
                Vencimiento.fecha_vencimiento <= fin_semana,
                Cliente.activo == True,
            )
            .order_by(Vencimiento.fecha_vencimiento)
            .all()
        )

        # Alertas activas
        alertas_activas = db.query(AlertaVencimiento).filter(
            AlertaVencimiento.resuelta_at == None
        ).count()

        alertas_criticas = db.query(AlertaVencimiento).filter(
            AlertaVencimiento.resuelta_at == None,
            AlertaVencimiento.nivel == "critica",
        ).count()

        # Clientes con documentación pendiente
        clientes_activos = db.query(Cliente).filter(Cliente.activo == True).count()

        # Construir email
        lineas = [
            f"<h2>Resumen semanal — {hoy.strftime('%d/%m/%Y')}</h2>",
            f"<p><b>Clientes activos:</b> {clientes_activos}</p>",
            f"<p><b>Alertas activas:</b> {alertas_activas} ({alertas_criticas} críticas)</p>",
            f"<h3>Vencimientos esta semana ({len(vencimientos_semana)})</h3>",
        ]

        if vencimientos_semana:
            lineas.append("<ul>")
            for v, c in vencimientos_semana[:20]:
                dias = (v.fecha_vencimiento - hoy).days
                lineas.append(f"<li>{v.tipo.value} — {c.nombre} ({v.fecha_vencimiento.strftime('%d/%m')} — {dias}d)</li>")
            lineas.append("</ul>")
        else:
            lineas.append("<p>Sin vencimientos pendientes esta semana.</p>")

        cuerpo = "\n".join(lineas)
        asunto = f"PyME OS — Resumen semanal ({hoy.strftime('%d/%m/%Y')})"

        try:
            _enviar_email(dueno.email, asunto, cuerpo)

            # Registrar en email_log
            from models.email_log import EmailLog
            db.add(EmailLog(
                recipient_type="studio",
                recipient_email=dueno.email,
                email_type="resumen_semanal",
                subject=asunto,
                status="sent",
            ))
            db.commit()
            logger.info("Job resumen semanal — email enviado a %s", dueno.email)
        except Exception as e:
            logger.error("Job resumen semanal — error enviando email: %s", e)

    except Exception as e:
        logger.error("Job resumen semanal — error general: %s", e)
    finally:
        db.close()
