"""
Servicio de optimización e IA para procesos.
Solo llamadas a Claude API — sin CRUD de base de datos.
El CRUD de Automatizacion vive en automatizacion_service.py.
"""
import json
import logging

import anthropic
from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.ai_client import get_anthropic_client

logger = logging.getLogger("pymeos")

_MODELO = "claude-haiku-4-5-20251001"


def _limpiar_json(raw: str) -> dict:
    """Limpia bloques markdown y parsea JSON. Patrón igual que email_clasificador.py."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


async def optimizar_descripcion(descripcion: str, db: Session | None = None) -> dict:
    """
    Recibe una descripción libre de un proceso y retorna un template estructurado
    con nombre, tipo sugerido, descripcion mejorada y pasos sugeridos.
    """
    prompt = f"""Sos un consultor de procesos para estudios contables argentinos.
El usuario describió un proceso de manera informal. Tu tarea es estructurarlo.

Devolvé ÚNICAMENTE este JSON, sin texto adicional ni bloques markdown:
{{
  "nombre": str,
  "tipo": str,
  "descripcion": str,
  "pasos": [
    {{
      "orden": int,
      "titulo": str,
      "descripcion": str,
      "tiempo_estimado_minutos": int,
      "es_automatizable": bool
    }}
  ]
}}

Tipos válidos: "onboarding" | "liquidacion_iva" | "balance" | "cierre_ejercicio" | "declaracion_ganancias" | "declaracion_iibb" | "otro"
Los pasos deben ser concretos, accionables y en orden lógico.
tiempo_estimado_minutos debe ser un entero razonable (entre 5 y 480).
es_automatizable: true si el paso puede hacerse con software sin intervención humana.

Descripción del proceso:
{descripcion}"""

    client = get_anthropic_client(db) if db else anthropic.AsyncAnthropic()
    mensaje = await client.messages.create(
        model=_MODELO,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _limpiar_json(mensaje.content[0].text)


_SYSTEM_PROMPT_OPTIMIZADOR = """Sos un experto en optimización de procesos para estudios contables argentinos (firmas de 5 a 50 empleados que brindan servicios de contabilidad, impuestos y laboral).

Tu marco de análisis es el Critical Client Flow: evaluás cada proceso desde la perspectiva del impacto en la experiencia del cliente del estudio, y si su demora o error genera incumplimientos fiscales (vencimientos AFIP, IIBB, Monotributo).

Criterios de recomendación en orden de prioridad:
1. Reducir riesgo de vencimientos fiscales (AFIP, IIBB, Monotributo, Ganancias)
2. Reducir tiempo total del proceso
3. Reducir dependencia de una sola persona (eliminar cuellos de botella individuales)
4. Identificar qué pasos son automatizables con n8n u otras herramientas de bajo código

Respondé SIEMPRE con un objeto JSON válido y nada más. Sin texto adicional, sin bloques markdown."""


async def analizar_pasos_automatizabilidad(pasos: list[dict], db: Session | None = None) -> dict:
    """
    Clasifica cada paso del proceso por nivel de automatizabilidad.
    Retorna análisis enriquecido: resumen, pasos_criticos, sugerencias, riesgo_fiscal, automatizable por paso.
    """
    pasos_texto = "\n".join(
        f"{p.get('orden', i+1)}. {p.get('titulo', '')} — {p.get('descripcion', '')}"
        for i, p in enumerate(pasos)
    )

    prompt = f"""Analizá cada paso del proceso y clasificá su automatizabilidad.

Devolvé ÚNICAMENTE este JSON con exactamente estos campos:
{{
  "resumen": str,
  "pasos_criticos": [str],
  "sugerencias": [str],
  "automatizable": bool,
  "riesgo_fiscal": bool,
  "pasos": [
    {{
      "orden": int,
      "automatizable": str,
      "herramienta_sugerida": str | null,
      "justificacion": str,
      "riesgo_fiscal": str,
      "ahorro_estimado_minutos": int
    }}
  ],
  "ahorro_total_horas_mes": float
}}

automatizable (raíz): true si al menos un paso del proceso puede automatizarse con n8n.
riesgo_fiscal (raíz): true si algún paso tiene alto riesgo de error fiscal si se automatiza mal.
automatizable (por paso): "si" | "parcial" | "no"
herramienta_sugerida: herramienta concreta (n8n, Make, Zapier, Python script, etc.) o null.
riesgo_fiscal (por paso): "alto" | "medio" | "bajo"
pasos_criticos: títulos de pasos que NO deben automatizarse por impacto fiscal.
sugerencias: recomendaciones de implementación para el estudio contable.
ahorro_total_horas_mes: horas mensuales estimadas si se automatizan todos los pasos posibles.

Pasos del proceso:
{pasos_texto}"""

    client = get_anthropic_client(db) if db else anthropic.AsyncAnthropic()
    mensaje = await client.messages.create(
        model=_MODELO,
        max_tokens=1500,
        system=_SYSTEM_PROMPT_OPTIMIZADOR,
        messages=[{"role": "user", "content": prompt}],
    )
    return _limpiar_json(mensaje.content[0].text)


async def generar_flujo_n8n(pasos: list[dict], analisis: dict, db: Session | None = None) -> dict:
    """
    Genera un workflow JSON compatible con n8n basado en los pasos y el análisis.
    Valida que el JSON tenga la estructura mínima requerida por n8n.
    """
    pasos_texto = "\n".join(
        f"{p.get('orden', i+1)}. {p.get('titulo', '')} — automatizable: {'si' if p.get('es_automatizable') else 'no'}"
        for i, p in enumerate(pasos)
    )

    prompt = f"""Generá un workflow JSON para n8n que automatice los pasos indicados.

Devolvé ÚNICAMENTE el JSON del workflow, sin texto adicional ni bloques markdown.
El JSON DEBE tener exactamente esta estructura raíz:
{{
  "nodes": [...],
  "connections": {{...}},
  "settings": {{...}}
}}

Cada nodo debe tener: id, name, type, position ([x, y]), parameters.
Usá nodos nativos de n8n cuando sea posible (HTTP Request, Code, Set, If, etc.).
Solo incluir pasos que tengan automatizabilidad "si" o "parcial".

Pasos a automatizar:
{pasos_texto}

Análisis de automatizabilidad:
{json.dumps(analisis, ensure_ascii=False, indent=2)[:2000]}"""

    client = get_anthropic_client(db) if db else anthropic.AsyncAnthropic()
    mensaje = await client.messages.create(
        model=_MODELO,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    flujo = _limpiar_json(mensaje.content[0].text)
    _validar_flujo_n8n(flujo)
    return flujo


def _validar_flujo_n8n(flujo: dict) -> None:
    """Verifica que el JSON tenga la estructura mínima requerida por n8n."""
    campos_requeridos = {"nodes", "connections", "settings"}
    faltantes = campos_requeridos - set(flujo.keys())
    if faltantes:
        raise HTTPException(
            status_code=422,
            detail=f"El flujo generado no tiene la estructura mínima de n8n. Faltan: {faltantes}",
        )


def _recalcular_ahorro(ahorro_claude: float, ahorro_propio: float) -> float:
    """
    Usa el valor del backend si difiere >20% del valor de Claude.
    Así evitamos valores inflados o inventados por el modelo.
    """
    if ahorro_propio <= 0:
        return ahorro_claude
    diferencia_relativa = abs(ahorro_claude - ahorro_propio) / ahorro_propio
    if diferencia_relativa > 0.20:
        logger.info(
            "optimizador: ahorro Claude (%.1f h) difiere >20%% del calculado (%.1f h) — usando valor propio",
            ahorro_claude, ahorro_propio,
        )
        return ahorro_propio
    return ahorro_claude
