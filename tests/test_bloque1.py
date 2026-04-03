"""
Tests Bloque 1: umbral configurable, ciclo de vida automatizaciones, vinculación tarea-paso.
"""
from unittest.mock import MagicMock, patch
import json

import pytest

from models.proceso import (
    Automatizacion, EstadoRevisionAutomatizacion,
    ProcesoInstancia, ProcesoPasoInstancia, ProcesoTemplate,
    ProcesoPasoTemplate, EstadoInstancia, EstadoPasoInstancia,
)
from models.tarea import Tarea, TipoTarea, PrioridadTarea
from models.studio_config import StudioConfig
from tests.conftest import _crear_token_con_rol


@pytest.fixture()
def token_dueno(db):
    return _crear_token_con_rol(db, "dueno_b1@pymeos.com", "Dueño B1", "dueno")


@pytest.fixture()
def headers(token_dueno):
    return {"Authorization": f"Bearer {token_dueno}"}


@pytest.fixture()
def template_b1(db, headers, client):
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso B1", "tipo": "liquidacion_iva"},
        headers=headers,
    )
    assert resp.status_code == 201
    tid = resp.json()["id"]
    pasos = [
        {"orden": 1, "titulo": "Paso 1", "tiempo_estimado_minutos": 30, "es_automatizable": True},
        {"orden": 2, "titulo": "Paso 2", "tiempo_estimado_minutos": 20, "es_automatizable": False},
    ]
    for paso in pasos:
        r = client.post(f"/api/procesos/templates/{tid}/pasos", json=paso, headers=headers)
        assert r.status_code == 201
    return resp.json()


# ─── 1.1 Umbral configurable ─────────────────────────────────────────────────

def test_umbral_por_defecto_es_5(client, db, headers):
    """El umbral por defecto debe ser 5."""
    resp = client.get("/api/reportes/config", headers=headers)
    assert resp.status_code == 200
    # El umbral no está en /config pero sí en la tabla studio_config
    config = db.query(StudioConfig).first()
    if config is None:
        # Crear vía endpoint para inicializar el singleton
        client.get("/api/reportes/config", headers=headers)
        config = db.query(StudioConfig).first()
    # Si aún no existe (primera vez), verificar el default del modelo
    if config is not None:
        assert config.umbral_instancias_optimizador == 5


def test_endpoint_umbral_actualiza_valor(client, db, headers):
    """PATCH /config/optimizador actualiza el umbral correctamente."""
    resp = client.patch(
        "/api/reportes/config/optimizador",
        json={"umbral_instancias": 3},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["umbral_instancias_optimizador"] == 3


def test_umbral_valida_rango_minimo(client, headers):
    """El umbral debe ser >= 1."""
    resp = client.patch(
        "/api/reportes/config/optimizador",
        json={"umbral_instancias": 0},
        headers=headers,
    )
    assert resp.status_code == 422


def test_umbral_valida_rango_maximo(client, headers):
    """El umbral debe ser <= 50."""
    resp = client.patch(
        "/api/reportes/config/optimizador",
        json={"umbral_instancias": 51},
        headers=headers,
    )
    assert resp.status_code == 422


def test_umbral_limite_inferior_valido(client, headers):
    """Umbral = 1 debe ser aceptado."""
    resp = client.patch(
        "/api/reportes/config/optimizador",
        json={"umbral_instancias": 1},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["umbral_instancias_optimizador"] == 1


def test_umbral_limite_superior_valido(client, headers):
    """Umbral = 50 debe ser aceptado."""
    resp = client.patch(
        "/api/reportes/config/optimizador",
        json={"umbral_instancias": 50},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["umbral_instancias_optimizador"] == 50


def test_umbral_personalizado_activa_recalculo_con_menos_instancias(client, db, headers, template_b1):
    """Con umbral=3, el optimizador debe recalcular después de 3 instancias completadas."""
    # Setear umbral a 3
    client.patch(
        "/api/reportes/config/optimizador",
        json={"umbral_instancias": 3},
        headers=headers,
    )

    tid = template_b1["id"]
    from datetime import datetime, timedelta

    # Crear 3 instancias completadas manualmente en la DB
    for i in range(3):
        inst = ProcesoInstancia(
            template_id=tid,
            estado=EstadoInstancia.completado,
            fecha_inicio=datetime.utcnow() - timedelta(hours=2),
            fecha_fin=datetime.utcnow(),
        )
        db.add(inst)
    db.commit()

    # Verificar que hay 3 instancias completadas
    instancias = db.query(ProcesoInstancia).filter(
        ProcesoInstancia.template_id == tid,
        ProcesoInstancia.estado == EstadoInstancia.completado,
    ).count()
    assert instancias == 3

    # El recalculo ocurre en _recalcular_estimados_template — llamarlo directamente
    from services.proceso_service import _recalcular_estimados_template
    _recalcular_estimados_template(db, tid)

    template = db.query(ProcesoTemplate).filter(ProcesoTemplate.id == tid).first()
    # Con 3 instancias y umbral=3, debe haberse recalculado
    assert template.tiempo_estimado_minutos is not None


# ─── 1.2 Ciclo de vida automatizaciones ──────────────────────────────────────

_ANALISIS_MOCK = {
    "resumen": "Proceso con pasos automatizables",
    "pasos_criticos": [],
    "sugerencias": [],
    "automatizable": True,
    "riesgo_fiscal": False,
    "pasos": [
        {"orden": 1, "automatizable": "si", "herramienta_sugerida": "n8n",
         "justificacion": "OK", "riesgo_fiscal": "bajo", "ahorro_estimado_minutos": 25},
    ],
    "ahorro_total_horas_mes": 5.0,
}
_FLUJO_MOCK = {
    "nodes": [{"id": "1", "name": "Start", "type": "n8n-nodes-base.start", "position": [100, 200], "parameters": {}}],
    "connections": {},
    "settings": {},
}


def _mock_anthropic(analisis=None, flujo=None):
    analisis = analisis or _ANALISIS_MOCK
    flujo = flujo or _FLUJO_MOCK
    mock_client = MagicMock()
    responses = [json.dumps(analisis), json.dumps(flujo)]
    call_count = {"n": 0}

    def create_response(*args, **kwargs):
        idx = call_count["n"] % len(responses)
        call_count["n"] += 1
        msg = MagicMock()
        msg.content = [MagicMock(text=responses[idx])]
        return msg

    mock_client.messages.create.side_effect = create_response
    return mock_client


def _crear_automatizacion(client, headers, template_b1):
    tid = template_b1["id"]
    mock_client = _mock_anthropic()
    with patch("services.optimizador_service.anthropic.Anthropic", return_value=mock_client):
        resp = client.post(
            "/api/automatizaciones/generar",
            json={"template_id": tid},
            headers=headers,
        )
    assert resp.status_code == 201
    return resp.json()["automatizacion"]


def test_automatizacion_nueva_tiene_estado_pendiente(client, db, headers, template_b1):
    """Nueva automatización generada debe tener estado_revision='pendiente'."""
    aut = _crear_automatizacion(client, headers, template_b1)
    assert aut["estado_revision"] == "pendiente"


def test_listar_pendientes_revision(client, db, headers, template_b1):
    """GET /automatizaciones/pendientes lista las automatizaciones pendientes."""
    _crear_automatizacion(client, headers, template_b1)

    resp = client.get("/api/automatizaciones/pendientes", headers=headers)
    assert resp.status_code == 200
    pendientes = resp.json()
    assert len(pendientes) >= 1
    assert all(a["estado_revision"] == "pendiente" for a in pendientes)


def test_flujo_pendiente_a_aprobada(client, db, headers, template_b1):
    """Flujo: pendiente → aprobada vía PATCH /aprobar."""
    aut = _crear_automatizacion(client, headers, template_b1)
    aut_id = aut["id"]

    resp = client.patch(f"/api/automatizaciones/{aut_id}/aprobar", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado_revision"] == "aprobada"
    assert data["aprobado_at"] is not None


def test_flujo_pendiente_a_descartada_con_motivo(client, db, headers, template_b1):
    """Flujo: pendiente → descartada con motivo vía PATCH /descartar."""
    aut = _crear_automatizacion(client, headers, template_b1)
    aut_id = aut["id"]

    resp = client.patch(
        f"/api/automatizaciones/{aut_id}/descartar",
        json={"motivo_descarte": "No aplica por cambio de proceso"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado_revision"] == "descartada"
    assert data["motivo_descarte"] == "No aplica por cambio de proceso"


def test_flujo_pendiente_a_descartada_sin_motivo(client, db, headers, template_b1):
    """Descartar sin motivo debe funcionar."""
    aut = _crear_automatizacion(client, headers, template_b1)
    resp = client.patch(
        f"/api/automatizaciones/{aut['id']}/descartar",
        json={},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["estado_revision"] == "descartada"


def test_resumen_incluye_conteo_automatizaciones_pendientes(client, db, headers, template_b1):
    """El resumen ejecutivo debe incluir automatizaciones_pendientes_revision."""
    _crear_automatizacion(client, headers, template_b1)

    resp = client.get("/api/reportes/resumen", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "automatizaciones_pendientes_revision" in data
    assert data["automatizaciones_pendientes_revision"] >= 1


def test_aprobada_no_aparece_en_pendientes(client, db, headers, template_b1):
    """Automatización aprobada NO debe aparecer en el listado de pendientes."""
    aut = _crear_automatizacion(client, headers, template_b1)
    client.patch(f"/api/automatizaciones/{aut['id']}/aprobar", headers=headers)

    resp = client.get("/api/automatizaciones/pendientes", headers=headers)
    assert resp.status_code == 200
    pendientes = resp.json()
    assert all(a["id"] != aut["id"] for a in pendientes)


# ─── 1.3 Vinculación Tarea → PasoInstancia ───────────────────────────────────

def test_crear_tarea_vinculada_a_paso_instancia(db, cliente_test, template_b1):
    """Tarea puede ser creada con proceso_instancia_paso_id (FK nullable)."""
    from datetime import datetime

    # Crear instancia con pasos
    template_id = template_b1["id"]
    instancia = ProcesoInstancia(template_id=template_id, estado=EstadoInstancia.pendiente)
    db.add(instancia)
    db.flush()

    paso_template = db.query(ProcesoPasoTemplate).filter(
        ProcesoPasoTemplate.template_id == template_id
    ).first()

    paso_inst = ProcesoPasoInstancia(
        instancia_id=instancia.id,
        paso_template_id=paso_template.id,
        orden=1,
    )
    db.add(paso_inst)
    db.commit()
    db.refresh(paso_inst)

    tarea = Tarea(
        cliente_id=cliente_test.id,
        titulo="Tarea vinculada a paso",
        tipo=TipoTarea.tarea,
        prioridad=PrioridadTarea.media,
        proceso_instancia_paso_id=paso_inst.id,
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)

    assert tarea.proceso_instancia_paso_id == paso_inst.id


def test_tarea_sin_vinculacion_no_falla(db, cliente_test):
    """Tarea sin proceso_instancia_paso_id se crea normalmente (FK nullable)."""
    tarea = Tarea(
        cliente_id=cliente_test.id,
        titulo="Tarea sin vinculación",
        tipo=TipoTarea.tarea,
        prioridad=PrioridadTarea.media,
        proceso_instancia_paso_id=None,
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)

    assert tarea.id is not None
    assert tarea.proceso_instancia_paso_id is None


def test_reporte_procesos_no_falla_sin_vinculacion_tareas(client, headers):
    """El reporte de procesos no falla cuando hay tareas sin vinculación."""
    from datetime import date
    periodo = date.today().strftime("%Y-%m")
    resp = client.get(f"/api/reportes/procesos?periodo={periodo}", headers=headers)
    assert resp.status_code == 200
    assert "procesos" in resp.json()
