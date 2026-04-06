import logging
import os
from datetime import date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from models.cliente import Cliente, CondicionFiscal
from models.documento import Documento, EstadoDocumento
from models.tarea import EstadoTarea, Tarea

logger = logging.getLogger("pymeos")


# Complejidad fiscal fija por condición
_COMPLEJIDAD_FISCAL = {
    CondicionFiscal.monotributista: 5,
    CondicionFiscal.responsable_inscripto: 12,
}
_COMPLEJIDAD_FISCAL_DEFAULT = 8


def _var1_dias_sin_actividad(db: Session, cliente_id: int) -> float:
    """25%: días desde la última tarea completada. Si no hay tareas, asume 45 días."""
    ultima = (
        db.query(Tarea.fecha_completada)
        .filter(
            Tarea.cliente_id == cliente_id,
            Tarea.estado == EstadoTarea.completada,
            Tarea.activo == True,
            Tarea.fecha_completada != None,
        )
        .order_by(Tarea.fecha_completada.desc())
        .first()
    )
    if ultima and ultima[0]:
        dias = (date.today() - ultima[0]).days
    else:
        dias = 45
    return min(dias / 45, 1.0) * 25


def _var2_documentacion_pendiente(db: Session, cliente_id: int) -> float:
    """30%: proporción de docs con estado problemático sobre el total."""
    docs = db.query(Documento).filter(
        Documento.cliente_id == cliente_id,
        Documento.activo == True,
    ).all()
    total = len(docs)
    if total == 0:
        return 0.0
    problematicos = sum(
        1 for d in docs
        if d.estado in (EstadoDocumento.pendiente, EstadoDocumento.requiere_revision)
    )
    return (problematicos / total) * 30


def _var3_historial_demoras(db: Session, cliente_id: int) -> float:
    """25%: proporción de tareas demoradas sobre completadas en últimos 90 días."""
    hace_90 = date.today() - timedelta(days=90)
    tareas = db.query(Tarea).filter(
        Tarea.cliente_id == cliente_id,
        Tarea.estado == EstadoTarea.completada,
        Tarea.activo == True,
        Tarea.fecha_completada >= hace_90,
    ).all()
    completadas = len(tareas)
    if completadas == 0:
        return 0.0
    demoradas = sum(
        1 for t in tareas
        if t.fecha_completada and t.fecha_limite
        and t.fecha_completada > t.fecha_limite
    )
    return (demoradas / completadas) * 25


def _var4_complejidad_fiscal(condicion: CondicionFiscal) -> float:
    """20%: valor fijo según condición fiscal."""
    return float(_COMPLEJIDAD_FISCAL.get(condicion, _COMPLEJIDAD_FISCAL_DEFAULT))


def _score_a_nivel(score: float) -> str:
    if score < 40:
        return "verde"
    if score < 70:
        return "amarillo"
    return "rojo"


def calcular_score_cliente(db: Session, cliente_id: int) -> dict:
    """Calcula y persiste el risk_score del cliente. risk_explanation se genera en background."""
    cliente = db.query(Cliente).filter(
        Cliente.id == cliente_id,
        Cliente.activo == True,
    ).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")

    v1 = _var1_dias_sin_actividad(db, cliente_id)
    v2 = _var2_documentacion_pendiente(db, cliente_id)
    v3 = _var3_historial_demoras(db, cliente_id)
    v4 = _var4_complejidad_fiscal(cliente.condicion_fiscal)

    score = round(v1 + v2 + v3 + v4, 2)
    nivel = _score_a_nivel(score)

    cliente.risk_score = score
    cliente.risk_level = nivel
    cliente.risk_calculated_at = datetime.utcnow()
    cliente.risk_explanation = None  # se regenera en background
    db.commit()

    factores = {
        "v1_dias_sin_actividad": round(v1, 2),
        "v2_docs_pendientes": round(v2, 2),
        "v3_historial_demoras": round(v3, 2),
        "v4_complejidad": round(v4, 2),
        "condicion_fiscal": cliente.condicion_fiscal.value if hasattr(cliente.condicion_fiscal, "value") else str(cliente.condicion_fiscal),
    }

    return {
        "id": cliente.id,
        "nombre": cliente.nombre,
        "cuit_cuil": cliente.cuit_cuil,
        "risk_score": score,
        "risk_level": nivel,
        "risk_explanation": None,
        "risk_calculated_at": cliente.risk_calculated_at.isoformat(),
        "_factores": factores,  # usado por el background task
    }


async def generar_risk_explanation_background(cliente_id: int, factores: dict) -> None:
    """
    Llama a Claude API para generar la explicación del risk score.
    Diseñado para correr como BackgroundTask — nunca bloquea el endpoint.
    """
    try:
        import anthropic
        from prompts.risk import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

        with SessionLocal() as db:
            cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
            if not cliente:
                return

            nivel_map = {"verde": "bajo", "amarillo": "moderado", "rojo": "alto"}
            nivel_texto = nivel_map.get(cliente.risk_level or "", cliente.risk_level or "")

            user_msg = USER_PROMPT_TEMPLATE.format(
                nombre=cliente.nombre,
                score=cliente.risk_score,
                nivel=nivel_texto,
                v1_dias_sin_actividad=factores.get("v1_dias_sin_actividad", 0),
                v2_docs_pendientes=factores.get("v2_docs_pendientes", 0),
                v3_historial_demoras=factores.get("v3_historial_demoras", 0),
                v4_complejidad=factores.get("v4_complejidad", 0),
                condicion_fiscal=factores.get("condicion_fiscal", ""),
            )

            client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=200,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            explanation = response.content[0].text.strip()

            cliente.risk_explanation = explanation
            db.commit()
            logger.info("risk_explanation generada para cliente id=%d", cliente_id)
    except Exception as e:
        logger.error("Error generando risk_explanation para cliente id=%d: %s", cliente_id, e)


def listar_clientes_por_riesgo(db: Session) -> list[dict]:
    """Clientes activos ordenados por risk_score descendente (rojos primero)."""
    clientes = db.query(Cliente).filter(Cliente.activo == True).all()
    resultado = [
        {
            "id": c.id,
            "nombre": c.nombre,
            "cuit_cuil": c.cuit_cuil,
            "risk_score": c.risk_score,
            "risk_level": c.risk_level,
            "risk_explanation": c.risk_explanation,
            "risk_calculated_at": c.risk_calculated_at.isoformat() if c.risk_calculated_at else None,
        }
        for c in clientes
    ]
    resultado.sort(key=lambda x: (x["risk_score"] is None, -(x["risk_score"] or 0)))
    return resultado


def recalcular_todos(db: Session) -> dict:
    """Recalcula el score de todos los clientes activos. Retorna conteo por nivel."""
    clientes = db.query(Cliente).filter(Cliente.activo == True).all()
    conteos = {"procesados": 0, "rojos": 0, "amarillos": 0, "verdes": 0}

    for cliente in clientes:
        v1 = _var1_dias_sin_actividad(db, cliente.id)
        v2 = _var2_documentacion_pendiente(db, cliente.id)
        v3 = _var3_historial_demoras(db, cliente.id)
        v4 = _var4_complejidad_fiscal(cliente.condicion_fiscal)
        score = round(v1 + v2 + v3 + v4, 2)
        nivel = _score_a_nivel(score)

        cliente.risk_score = score
        cliente.risk_level = nivel
        cliente.risk_calculated_at = datetime.utcnow()

        conteos["procesados"] += 1
        conteos[{"verde": "verdes", "amarillo": "amarillos", "rojo": "rojos"}[nivel]] += 1

    db.commit()
    return conteos
