"""
Adaptador Email: envía emails salientes usando la infraestructura SMTP existente.
Los emails entrantes llegan vía POST /api/asistente/mensaje (normalizado por n8n o integración directa).
"""
import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("pymeos")

MAIL_FROM = os.environ.get("MAIL_FROM", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def smtp_configurado() -> bool:
    return all([MAIL_FROM, SMTP_HOST, SMTP_USER, SMTP_PASSWORD])


def send_email(to: str, subject: str, body_text: str, nombre_estudio: str = "") -> bool:
    """
    Envía un email de texto plano usando SMTP.
    Retorna True si el envío fue exitoso.
    """
    if not smtp_configurado():
        logger.warning("SMTP no configurado, email a %s no enviado", to)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{nombre_estudio} <{MAIL_FROM}>" if nombre_estudio else MAIL_FROM
        msg["To"] = to

        # Versión HTML básica del cuerpo de texto
        html_body = f"<p style='font-family:Arial,sans-serif;'>{body_text.replace(chr(10), '<br>')}</p>"
        msg.attach(MIMEText(body_text, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(MAIL_FROM, to, msg.as_string())

        logger.info("Email enviado a %s — asunto: %s", to, subject)
        return True
    except Exception as e:
        logger.error("Error enviando email a %s: %s", to, e)
        return False
