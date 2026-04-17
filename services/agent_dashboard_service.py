import json
import logging
import os
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models.dashboard_conversation import DashboardConversation
from services import alert_service, profitability_service, risk_service

logger = logging.getLogger("pymeos")

_FALLBACK_RESPONSE = {
    "response": "No pude procesar tu consulta en este momento. Intentá de nuevo.",
    "suggested_actions": [],
    "data_referenced": [],
}


def obtener_contexto_estudio(db: Session) -> dict:
    """Construye el contexto de datos del estudio usando servicios especializados."""
    from models.cliente import Cliente
    from models.vencimiento import EstadoVencimiento, Vencimiento

    hoy = date.today()
    proximos_7 = hoy + timedelta(days=7)

    # Vencimientos próximos 7 días
    vencimientos = (
        db.query(Vencimiento, Cliente)
        .join(Cliente, Vencimiento.cliente_id == Cliente.id)
        .filter(
            Vencimiento.estado == EstadoVencimiento.pendiente,
            Vencimiento.fecha_vencimiento <= proximos_7,
            Cliente.activo == True,
        )
        .order_by(Vencimiento.fecha_vencimiento)
        .limit(10)
        .all()
    )
    venc_list = [
        {
            "cliente": v[1].nombre,
            "tipo": v[0].tipo.value if hasattr(v[0].tipo, "value") else str(v[0].tipo),
            "fecha": v[0].fecha_vencimiento.isoformat(),
            "dias_restantes": (v[0].fecha_vencimiento - hoy).days,
        }
        for v in vencimientos
    ]

    # Alertas activas — usa alert_service
    try:
        resumen = alert_service.resumen_alertas(db, studio_id)
    except Exception:
        resumen = {"criticas": 0, "advertencias": 0, "informativas": 0}

    # Top 5 clientes por rentabilidad — usa profitability_service
    periodo_actual = hoy.strftime("%Y-%m")
    try:
        rentabilidades = profitability_service.listar_rentabilidad(db, periodo_actual, studio_id or 0)
        top_clientes = [
            {
                "cliente": r.get("nombre", ""),
                "margen_pct": r.get("profit_margin_percentage"),
                "horas_reales": r.get("horas_reales"),
            }
            for r in (rentabilidades[:5] if rentabilidades else [])
        ]
    except Exception:
        top_clientes = []

    # Risk score promedio — usa risk_service
    try:
        scores = risk_service.listar_clientes_por_riesgo(db, studio_id)
        if scores:
            avg_risk = round(sum(s.get("risk_score", 0) for s in scores) / len(scores), 1)
            clientes_rojo = sum(1 for s in scores if s.get("risk_level") == "rojo")
        else:
            avg_risk = None
            clientes_rojo = 0
    except Exception:
        avg_risk = None
        clientes_rojo = 0

    return {
        "vencimientos_proximos_7_dias": venc_list,
        "alertas": resumen,
        "top_5_clientes_rentabilidad": top_clientes,
        "risk_score_promedio": avg_risk,
        "clientes_en_riesgo_rojo": clientes_rojo,
        "periodo": periodo_actual,
    }


async def chat(
    db: Session,
    studio_id: int | None,
    message: str,
    context: dict,
    conversation_history: list[dict],
    session_id: str,
) -> dict:
    """
    Procesa un mensaje del usuario y retorna la respuesta del agente.
    Guarda el intercambio en dashboard_conversations.
    """
    try:
        import anthropic
        from prompts.conocimiento_fiscal import CONOCIMIENTO_FISCAL_AR
        from prompts.conocimiento_plataforma import CONOCIMIENTO_PLATAFORMA
        from prompts.conocimiento_metricas import CONOCIMIENTO_METRICAS

        datos_contexto = obtener_contexto_estudio(db)

        # Obtener nombre del estudio desde la DB
        try:
            from models.studio import Studio
            studio_db = db.query(Studio).filter(Studio.id == studio_id).first()
            nombre_estudio = studio_db.nombre if studio_db else os.environ.get("STUDIO_NAME", "el estudio")
            modelo = (studio_db.claude_modelo if studio_db and studio_db.claude_modelo else None) or "claude-sonnet-4-6"
            api_key = (studio_db.claude_api_key_encrypted if studio_db else None) or os.environ.get("ANTHROPIC_API_KEY", "")
        except Exception:
            nombre_estudio = os.environ.get("STUDIO_NAME", "el estudio")
            modelo = "claude-sonnet-4-6"
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        hoy_str = date.today().strftime("%d/%m/%Y")
        snapshot = json.dumps(datos_contexto, ensure_ascii=False, indent=2)

        system_prompt = f"""Sos el asistente de inteligencia del estudio contable {nombre_estudio}.
Tenés acceso a los datos reales del estudio al día de hoy.
Tu rol es interpretar esos datos, detectar problemas y ayudar al contador a tomar decisiones concretas.

{CONOCIMIENTO_FISCAL_AR}

{CONOCIMIENTO_PLATAFORMA}

{CONOCIMIENTO_METRICAS}

DATOS ACTUALES DEL ESTUDIO — {hoy_str}:
{snapshot}

REGLAS DE RESPUESTA:
- Respondé siempre en español rioplatense, tono directo y profesional
- Máximo 150 palabras por respuesta salvo que te pidan más detalle
- Siempre citá datos concretos del estudio cuando los tengas disponibles
- Cuando identifiques un problema, sugerí UNA acción concreta con la ruta exacta en la plataforma
- Si el contador pregunta algo que no está en los datos, decilo claramente
- No inventes datos ni estimes valores que no estén en el snapshot
- Al final de cada respuesta, si corresponde, incluí 1-2 acciones concretas con su ruta"""

        messages = []
        for msg in conversation_history[-20:]:
            if msg.get("role") in ("user", "assistant") and msg.get("content"):
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=modelo,
            max_tokens=1000,
            system=system_prompt,
            messages=messages,
        )
        assistant_text = response.content[0].text.strip()

        _guardar_mensajes(db, studio_id, session_id, message, assistant_text, context)

        return {
            "response": assistant_text,
            "suggested_actions": [],
            "data_referenced": list(datos_contexto.keys()),
        }

    except Exception as e:
        logger.error("Error en dashboard agent chat: %s", e)
        _guardar_mensajes(db, studio_id, session_id, message, _FALLBACK_RESPONSE["response"], context)
        return _FALLBACK_RESPONSE


def _guardar_mensajes(
    db: Session,
    studio_id: int | None,
    session_id: str,
    user_message: str,
    assistant_message: str,
    context: dict,
) -> None:
    try:
        db.add(DashboardConversation(
            studio_id=studio_id,
            session_id=session_id,
            role="user",
            content=user_message,
            context_snapshot=context,
        ))
        db.add(DashboardConversation(
            studio_id=studio_id,
            session_id=session_id,
            role="assistant",
            content=assistant_message,
        ))
        db.commit()
    except Exception as e:
        logger.error("Error guardando conversación dashboard: %s", e)
