"""
Llama a Claude API para interpretar el mensaje del usuario.
Retorna JSON estructurado con intención, entidades y respuesta.
"""
import json
import logging
import os

logger = logging.getLogger("pymeos")

_FALLBACK_EMPLEADO = {
    "intencion": "desconocida",
    "entidades": {},
    "ambiguedad": False,
    "respuesta": "No pude procesar tu mensaje. Intentá de nuevo o escribí de forma más concisa.",
    "requiere_confirmacion": False,
    "operacion_a_confirmar": None,
}

_FALLBACK_CLIENTE = {
    "intencion": "desconocida",
    "respuesta_email": {
        "asunto": "Re: su consulta",
        "cuerpo": "Estimado cliente, recibimos su mensaje. Un miembro del equipo le responderá a la brevedad.",
    },
    "adjuntos_recibidos": None,
}


async def interpretar_empleado(mensaje: str, contexto_datos: dict, nombre_empleado: str, rol: str) -> dict:
    """Interpreta un mensaje de empleado vía Telegram."""
    try:
        import anthropic
        from prompts.asistente_empleado import SYSTEM_PROMPT_TEMPLATE

        import json as _json
        system = SYSTEM_PROMPT_TEMPLATE.format(
            nombre_empleado=nombre_empleado,
            rol=rol,
            nombre_estudio=os.environ.get("STUDIO_NAME", "el estudio"),
            contexto_datos=_json.dumps(contexto_datos, ensure_ascii=False),
        )

        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=500,
            system=system,
            messages=[{"role": "user", "content": mensaje}],
        )
        raw = response.content[0].text.strip()

        # Extraer JSON de la respuesta
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        return _FALLBACK_EMPLEADO

    except Exception as e:
        logger.error("Error en interprete empleado: %s", e)
        return _FALLBACK_EMPLEADO


async def interpretar_cliente(mensaje: str, contexto_datos: dict, nombre_estudio: str) -> dict:
    """Interpreta un mensaje de cliente vía Email."""
    try:
        import anthropic
        from prompts.asistente_cliente import SYSTEM_PROMPT_TEMPLATE

        system = SYSTEM_PROMPT_TEMPLATE.format(
            nombre_estudio=nombre_estudio,
            nombre_cliente=contexto_datos.get("nombre_cliente", ""),
            cuit_cliente=contexto_datos.get("cuit_cliente", ""),
            docs_recibidos=contexto_datos.get("docs_recibidos", []),
            docs_pendientes=contexto_datos.get("docs_pendientes", []),
            proximo_vencimiento=contexto_datos.get("proximo_vencimiento", "sin vencimientos próximos"),
            estado_proceso=contexto_datos.get("estado_proceso", "sin procesos activos"),
        )

        client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=system,
            messages=[{"role": "user", "content": mensaje}],
        )
        raw = response.content[0].text.strip()

        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        return _FALLBACK_CLIENTE

    except Exception as e:
        logger.error("Error en interprete cliente: %s", e)
        return _FALLBACK_CLIENTE
