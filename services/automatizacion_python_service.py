"""
Servicio para el builder de automatizaciones Python visuales.
Genera grafos de nodos desde descripciones de texto usando Claude,
y genera código Python ejecutable a partir del grafo.
"""
import json
import logging
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models.automatizacion_python import AutomatizacionPython, EstadoAutomatizacionPython
from schemas.automatizacion_python import (
    AutomatizacionPythonCreate,
    AutomatizacionPythonUpdate,
)

logger = logging.getLogger("pymeos")

_MODELO = "claude-haiku-4-5-20251001"

# Tipos de nodo disponibles en el canvas visual
TIPOS_NODO = {
    "trigger": "Disparador — inicia el flujo (cron, webhook, evento)",
    "http_request": "Llamada HTTP — GET/POST a una API externa",
    "transform": "Transformación — modifica o mapea datos",
    "filter": "Filtro — condición para continuar o detener el flujo",
    "notify": "Notificación — envío de email, Telegram, etc.",
    "code": "Código Python personalizado",
    "delay": "Demora — espera un tiempo antes de continuar",
    "condition": "Bifurcación — ramifica el flujo según una condición",
    "db_query": "Consulta a la base de datos del estudio",
    "file_read": "Lectura de archivo o documento",
}


def _limpiar_json(raw: str) -> dict | list:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def crear_automatizacion_python(
    db: Session,
    data: AutomatizacionPythonCreate,
    empleado_id: Optional[int] = None,
    studio_id: int = None,
) -> AutomatizacionPython:
    auto = AutomatizacionPython(
        studio_id=studio_id,
        nombre=data.nombre,
        descripcion=data.descripcion,
        creado_por_id=empleado_id,
        nodos=data.nodos or [],
        conexiones=data.conexiones or [],
    )
    db.add(auto)
    db.commit()
    db.refresh(auto)
    return auto


def listar_automatizaciones_python(db: Session, studio_id: int = None) -> list[AutomatizacionPython]:
    filtros = [AutomatizacionPython.estado != EstadoAutomatizacionPython.archivado]
    if studio_id is not None:
        filtros.append(AutomatizacionPython.studio_id == studio_id)
    return (
        db.query(AutomatizacionPython)
        .filter(*filtros)
        .order_by(AutomatizacionPython.updated_at.desc())
        .all()
    )


def obtener_automatizacion_python(db: Session, auto_id: int, studio_id: int = None) -> AutomatizacionPython:
    filtros = [AutomatizacionPython.id == auto_id]
    if studio_id is not None:
        filtros.append(AutomatizacionPython.studio_id == studio_id)
    auto = db.query(AutomatizacionPython).filter(*filtros).first()
    if not auto:
        raise HTTPException(status_code=404, detail="Automatización Python no encontrada.")
    return auto


def actualizar_automatizacion_python(
    db: Session,
    auto_id: int,
    data: AutomatizacionPythonUpdate,
) -> AutomatizacionPython:
    auto = obtener_automatizacion_python(db, auto_id)
    if data.nombre is not None:
        auto.nombre = data.nombre
    if data.descripcion is not None:
        auto.descripcion = data.descripcion
    if data.estado is not None:
        auto.estado = data.estado
    if data.nodos is not None:
        auto.nodos = data.nodos
    if data.conexiones is not None:
        auto.conexiones = data.conexiones
    db.commit()
    db.refresh(auto)
    return auto


def aplicar_inputs(db: Session, auto_id: int, inputs: dict) -> AutomatizacionPython:
    """Guarda los valores de inputs provistos por el usuario para los nodos que los requieren."""
    auto = obtener_automatizacion_python(db, auto_id)
    configurados = auto.inputs_configurados or {}
    for node_id, valores in inputs.items():
        configurados[node_id] = {**(configurados.get(node_id) or {}), **valores}
    auto.inputs_configurados = configurados
    db.commit()
    db.refresh(auto)
    return auto


def obtener_inputs_requeridos(db: Session, auto_id: int) -> list[dict]:
    """
    Retorna los required_inputs de todos los nodos que aún no tienen sus valores configurados.
    """
    auto = obtener_automatizacion_python(db, auto_id)
    nodos = auto.nodos or []
    configurados = auto.inputs_configurados or {}
    pendientes = []

    for nodo in nodos:
        node_id = nodo.get("id", "")
        required = nodo.get("required_inputs", [])
        if not required:
            continue
        valores_node = configurados.get(node_id, {})
        campos_pendientes = [
            r for r in required
            if r.get("campo") not in valores_node or not valores_node[r.get("campo")]
        ]
        if campos_pendientes:
            pendientes.append({
                "node_id": node_id,
                "node_name": nodo.get("name", node_id),
                "node_type": nodo.get("type", ""),
                "campos": campos_pendientes,
            })

    return pendientes


# ─── Generación con IA ────────────────────────────────────────────────────────

async def generar_grafo_desde_descripcion(
    db: Session,
    descripcion: str,
    nombre: Optional[str],
    empleado_id: Optional[int],
    studio_id: int = None,
) -> AutomatizacionPython:
    """
    Usa Claude para generar un grafo de nodos Python a partir de una descripción textual.
    Persiste el resultado como AutomatizacionPython en estado borrador.
    """
    from services.ai_client import get_anthropic_client
    import anthropic as _anthropic

    tipos_txt = "\n".join(f"- {k}: {v}" for k, v in TIPOS_NODO.items())

    prompt = f"""Sos un experto en automatización de procesos para estudios contables argentinos.
El usuario describió una automatización. Tu tarea es generar un grafo de nodos Python.

Tipos de nodos disponibles:
{tipos_txt}

Para cada nodo donde sea necesario, incluí en "required_inputs" los campos que el usuario deberá configurar
(por ejemplo: API keys, URLs, credenciales, parámetros de conexión).

Devolvé ÚNICAMENTE este JSON (sin texto adicional, sin markdown):
{{
  "nombre": "string — nombre descriptivo de la automatización",
  "descripcion": "string — qué hace esta automatización",
  "nodos": [
    {{
      "id": "node_1",
      "type": "uno de los tipos listados arriba",
      "name": "nombre legible del nodo",
      "position": {{"x": 100, "y": 200}},
      "config": {{}},
      "required_inputs": [
        {{"campo": "nombre_campo", "label": "Texto para el usuario", "tipo": "text|password|url|number"}}
      ]
    }}
  ],
  "conexiones": [
    {{"from_node": "node_1", "to_node": "node_2", "label": null}}
  ]
}}

Reglas:
- Posicioná los nodos en una grilla horizontal con x incrementando de 200 en 200 y y=200 para flujo lineal.
  Para bifurcaciones usá y distintos.
- El primer nodo siempre debe ser tipo "trigger".
- Incluí required_inputs solo cuando realmente se necesite configuración del usuario.
- Máximo 12 nodos. Flujo realista y ejecutable en Python.

Descripción de la automatización:
{descripcion}"""

    try:
        client = get_anthropic_client(db)
    except HTTPException:
        client = _anthropic.AsyncAnthropic()

    mensaje = await client.messages.create(
        model=_MODELO,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )

    try:
        datos = _limpiar_json(mensaje.content[0].text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"La IA devolvió una respuesta que no es JSON válido: {exc}",
        )

    auto = AutomatizacionPython(
        studio_id=studio_id,
        nombre=nombre or datos.get("nombre", "Nueva automatización"),
        descripcion=datos.get("descripcion"),
        creado_por_id=empleado_id,
        nodos=datos.get("nodos", []),
        conexiones=datos.get("conexiones", []),
        estado=EstadoAutomatizacionPython.borrador,
    )
    db.add(auto)
    db.commit()
    db.refresh(auto)
    return auto


async def generar_codigo_python(db: Session, auto_id: int) -> AutomatizacionPython:
    """
    Genera código Python ejecutable a partir del grafo de nodos de la automatización.
    El código usa los inputs_configurados del usuario para llenar las variables.
    """
    from services.ai_client import get_anthropic_client
    import anthropic as _anthropic

    auto = obtener_automatizacion_python(db, auto_id)
    nodos = auto.nodos or []
    conexiones = auto.conexiones or []
    inputs_configurados = auto.inputs_configurados or {}

    if not nodos:
        raise HTTPException(status_code=400, detail="La automatización no tiene nodos definidos.")

    # Construir descripción del grafo para Claude
    nodos_desc = []
    for nodo in nodos:
        node_id = nodo.get("id", "")
        config = nodo.get("config", {})
        inputs_vals = inputs_configurados.get(node_id, {})
        config_completo = {**config, **inputs_vals}
        nodos_desc.append(
            f"- Nodo {node_id} (tipo={nodo.get('type')}, nombre={nodo.get('name')}): config={json.dumps(config_completo, ensure_ascii=False)}"
        )

    conexiones_desc = [
        f"  {c.get('from_node')} → {c.get('to_node')}" + (f" [{c.get('label')}]" if c.get("label") else "")
        for c in conexiones
    ]

    prompt = f"""Generá código Python para ejecutar la siguiente automatización.

Nodos del flujo:
{chr(10).join(nodos_desc)}

Conexiones (flujo de ejecución):
{chr(10).join(conexiones_desc) if conexiones_desc else "  (flujo lineal según orden de nodos)"}

Reglas para el código:
1. Cada nodo debe ser una función Python con su id como nombre (con _ en lugar de guiones).
2. El script principal llama las funciones en orden según las conexiones.
3. Usar httpx para HTTP requests (no requests).
4. Usar variables para todos los valores configurables, con comentarios indicando dónde ingresarlos.
5. Incluir manejo de errores básico con try/except en cada nodo.
6. El código debe ser completo y ejecutable (no pseudocódigo).
7. Agregar docstrings breves a cada función.
8. Al inicio del script, incluir un bloque de configuración con todas las variables que el usuario debe completar.

Devolvé ÚNICAMENTE el código Python (sin markdown, sin explicaciones)."""

    try:
        client = get_anthropic_client(db)
    except HTTPException:
        client = _anthropic.AsyncAnthropic()

    mensaje = await client.messages.create(
        model=_MODELO,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}],
    )

    codigo = mensaje.content[0].text.strip()
    # Limpiar markdown si Claude lo agrega
    if codigo.startswith("```"):
        partes = codigo.split("```")
        codigo = partes[1] if len(partes) > 1 else codigo
        if codigo.startswith("python"):
            codigo = codigo[6:]
        codigo = codigo.strip()

    auto.codigo_generado = codigo
    db.commit()
    db.refresh(auto)
    return auto
