"""
Servicio de optimización e IA para procesos.
Solo llamadas a Claude API — sin CRUD de base de datos.
El CRUD de Automatizacion vive en automatizacion_service.py.
"""
import json
import logging

import anthropic
from fastapi import HTTPException

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


def optimizar_descripcion(descripcion: str) -> dict:
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

    client = anthropic.Anthropic()
    mensaje = client.messages.create(
        model=_MODELO,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _limpiar_json(mensaje.content[0].text)


def analizar_pasos_automatizabilidad(pasos: list[dict]) -> dict:
    """
    Clasifica cada paso del proceso por nivel de automatizabilidad.
    Retorna análisis con herramienta sugerida y justificación.
    """
    pasos_texto = "\n".join(
        f"{p.get('orden', i+1)}. {p.get('titulo', '')} — {p.get('descripcion', '')}"
        for i, p in enumerate(pasos)
    )

    prompt = f"""Sos un experto en automatización de procesos contables en Argentina.
Analizá cada paso y clasificá su automatizabilidad.

Devolvé ÚNICAMENTE este JSON, sin texto adicional ni bloques markdown:
{{
  "resumen": str,
  "pasos": [
    {{
      "orden": int,
      "automatizabilidad": str,
      "herramienta_sugerida": str | null,
      "justificacion": str,
      "ahorro_estimado_minutos": int
    }}
  ],
  "ahorro_total_horas_mes": float
}}

automatizabilidad: "si" | "parcial" | "no"
herramienta_sugerida: nombre de herramienta (n8n, Make, Zapier, Python script, etc.) o null si no es automatizable.
ahorro_total_horas_mes: horas mensuales estimadas que se ahorrarían si se automatizan todos los pasos posibles.

Pasos del proceso:
{pasos_texto}"""

    client = anthropic.Anthropic()
    mensaje = client.messages.create(
        model=_MODELO,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _limpiar_json(mensaje.content[0].text)


def generar_flujo_n8n(pasos: list[dict], analisis: dict) -> dict:
    """
    Genera un workflow JSON compatible con n8n basado en los pasos y el análisis.
    Valida que el JSON tenga la estructura mínima requerida por n8n.
    """
    pasos_texto = "\n".join(
        f"{p.get('orden', i+1)}. {p.get('titulo', '')} — automatizabilidad: {p.get('automatizabilidad', 'desconocida')}"
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

    client = anthropic.Anthropic()
    mensaje = client.messages.create(
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
