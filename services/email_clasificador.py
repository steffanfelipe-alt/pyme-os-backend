"""
Clasificador de emails entrantes con Claude API.
Sigue el mismo patrón que _clasificar_con_ia() en documento_service.py.
"""
import json
import logging
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from services.ai_client import get_anthropic_client

logger = logging.getLogger("pymeos")

_PROMPT_CLASIFICACION = """Sos un asistente especializado en la gestión de un estudio contable argentino.
Analizá este email y devolvé ÚNICAMENTE este JSON, sin texto adicional ni bloques markdown:
{{
  "categoria": str,
  "urgencia": str,
  "resumen": str,
  "remitente_tipo": str,
  "requiere_respuesta": bool,
  "borrador_respuesta": str | null,
  "cliente_cuit": str | null,
  "confianza": float
}}

Categorías válidas: "documento_recibido" | "consulta_fiscal" | "postulacion_laboral" | "solicitud_licencia" | "consulta_interna" | "proveedor" | "notificacion_afip" | "spam" | "otro"
Urgencia: "alta" | "media" | "baja"
Remitente tipo: "cliente_registrado" | "postulante" | "proveedor" | "organismos" | "desconocido"
Resumen: máximo 2 oraciones en español, tono profesional.
Borrador de respuesta: solo si requiere_respuesta es true. Redactar en nombre del estudio, en español, tono profesional pero cálido. null si no requiere respuesta.
Cliente CUIT: si el remitente coincide con alguno de los clientes listados, devolver su CUIT. null si no matchea.

Clientes registrados del estudio: {clientes_registrados}

Email a analizar:
De: {remitente}
Asunto: {asunto}
Cuerpo: {cuerpo}"""

# Umbral de confianza bajo el cual se marca revisión manual
_UMBRAL_CONFIANZA = 0.5


async def clasificar_email(
    remitente: str,
    asunto: str,
    cuerpo: str,
    clientes_registrados: list[dict],
    db: Session | None = None,
) -> dict[str, Any]:
    """
    Llama a Claude API para clasificar un email entrante.

    Args:
        remitente: Dirección de email del remitente.
        asunto: Asunto del email.
        cuerpo: Cuerpo en texto plano (max recomendado: 4000 chars).
        clientes_registrados: Lista de dicts con {nombre, cuit_cuil} del estudio.

    Returns:
        Dict con los campos del JSON de clasificación + `requiere_revision_manual` y `motivo_revision`.
    """
    lista_clientes = ", ".join(
        f"{c['nombre']} ({c['cuit_cuil']})" for c in clientes_registrados
    ) or "ninguno"

    prompt = _PROMPT_CLASIFICACION.format(
        clientes_registrados=lista_clientes,
        remitente=remitente,
        asunto=asunto or "(sin asunto)",
        cuerpo=cuerpo[:4000] if cuerpo else "(sin cuerpo)",
    )

    client = get_anthropic_client(db) if db else anthropic.AsyncAnthropic()
    mensaje = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = mensaje.content[0].text.strip()
    # Limpiar bloques markdown si Claude los agrega
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    resultado = json.loads(raw)

    # Determinar si requiere revisión manual
    confianza = resultado.get("confianza", 1.0)
    urgencia = resultado.get("urgencia", "baja")
    remitente_tipo = resultado.get("remitente_tipo", "desconocido")

    requiere_revision = False
    motivo = None

    if urgencia == "alta":
        requiere_revision = True
        motivo = "urgencia_alta"
    elif confianza < _UMBRAL_CONFIANZA:
        requiere_revision = True
        motivo = "confianza_baja"
    elif remitente_tipo == "desconocido":
        requiere_revision = True
        motivo = "remitente_desconocido"

    resultado["requiere_revision_manual"] = requiere_revision
    resultado["motivo_revision"] = motivo
    return resultado
