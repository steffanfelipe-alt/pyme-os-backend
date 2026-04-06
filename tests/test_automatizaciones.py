"""
Tests para el módulo de automatizaciones.
Mockea anthropic.Anthropic() para evitar llamadas reales a la API.
"""
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import _crear_token_con_rol


@pytest.fixture()
def token_dueno_auto(db):
    return _crear_token_con_rol(db, "dueno_aut@pymeos.com", "Dueño Auto", "dueno")


@pytest.fixture()
def template_con_pasos_auto(client, db, token_dueno_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso Automatizable", "tipo": "liquidacion_iva"},
        headers=headers,
    )
    assert resp.status_code == 201
    tid = resp.json()["id"]
    pasos = [
        {"orden": 1, "titulo": "Descargar reportes", "tiempo_estimado_minutos": 20, "es_automatizable": True},
        {"orden": 2, "titulo": "Revisar manualmente", "tiempo_estimado_minutos": 45, "es_automatizable": False},
    ]
    for paso in pasos:
        r = client.post(f"/api/procesos/templates/{tid}/pasos", json=paso, headers=headers)
        assert r.status_code == 201
    return resp.json()


def _mock_anthropic_client(analisis_return: dict, flujo_return: dict):
    """Crea un mock de anthropic.AsyncAnthropic() que retorna respuestas predefinidas."""
    import json
    from unittest.mock import AsyncMock

    mock_client = MagicMock()
    responses = [
        json.dumps(analisis_return),
        json.dumps(flujo_return),
    ]
    call_count = {"n": 0}

    async def create_response(*args, **kwargs):
        idx = call_count["n"] % len(responses)
        call_count["n"] += 1
        msg = MagicMock()
        msg.content = [MagicMock(text=responses[idx])]
        return msg

    mock_client.messages.create = AsyncMock(side_effect=create_response)
    return mock_client


_ANALISIS_MOCK = {
    "resumen": "El proceso tiene pasos automatizables",
    "pasos": [
        {"orden": 1, "automatizabilidad": "si", "herramienta_sugerida": "n8n", "justificacion": "Descarga automática", "ahorro_estimado_minutos": 18},
        {"orden": 2, "automatizabilidad": "no", "herramienta_sugerida": None, "justificacion": "Requiere criterio", "ahorro_estimado_minutos": 0},
    ],
    "ahorro_total_horas_mes": 6.0,
}

_FLUJO_MOCK = {
    "nodes": [
        {"id": "1", "name": "Start", "type": "n8n-nodes-base.start", "position": [100, 200], "parameters": {}},
        {"id": "2", "name": "HTTP Request", "type": "n8n-nodes-base.httpRequest", "position": [300, 200], "parameters": {"url": "https://api.example.com"}},
    ],
    "connections": {"Start": {"main": [[{"node": "HTTP Request", "type": "main", "index": 0}]]}},
    "settings": {"executionOrder": "v1"},
}


def test_generar_automatizacion(client, token_dueno_auto, template_con_pasos_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    tid = template_con_pasos_auto["id"]

    mock_client = _mock_anthropic_client(_ANALISIS_MOCK, _FLUJO_MOCK)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        resp = client.post(
            "/api/automatizaciones/generar",
            json={"template_id": tid},
            headers=headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["requiere_revision"] is True
    assert "revisá" in data["mensaje"].lower() or "revisar" in data["mensaje"].lower() or "revisá" in data["mensaje"]
    aut = data["automatizacion"]
    assert aut["template_id"] == tid
    assert aut["flujo_json"] is not None
    assert aut["analisis_pasos"] is not None
    assert aut["ahorro_horas_mes"] > 0


def test_listar_automatizaciones(client, token_dueno_auto, template_con_pasos_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    tid = template_con_pasos_auto["id"]

    mock_client = _mock_anthropic_client(_ANALISIS_MOCK, _FLUJO_MOCK)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        client.post("/api/automatizaciones/generar", json={"template_id": tid}, headers=headers)

    resp = client.get("/api/automatizaciones", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_obtener_automatizacion_por_id(client, token_dueno_auto, template_con_pasos_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    tid = template_con_pasos_auto["id"]

    mock_client = _mock_anthropic_client(_ANALISIS_MOCK, _FLUJO_MOCK)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        gen_resp = client.post("/api/automatizaciones/generar", json={"template_id": tid}, headers=headers)
    aut_id = gen_resp.json()["automatizacion"]["id"]

    resp = client.get(f"/api/automatizaciones/{aut_id}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == aut_id


def test_actualizar_estado_automatizacion(client, token_dueno_auto, template_con_pasos_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    tid = template_con_pasos_auto["id"]

    mock_client = _mock_anthropic_client(_ANALISIS_MOCK, _FLUJO_MOCK)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        gen_resp = client.post("/api/automatizaciones/generar", json={"template_id": tid}, headers=headers)
    aut_id = gen_resp.json()["automatizacion"]["id"]

    resp = client.put(f"/api/automatizaciones/{aut_id}", json={"estado": "activa"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["estado"] == "activa"


def test_eliminar_automatizacion(client, token_dueno_auto, template_con_pasos_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    tid = template_con_pasos_auto["id"]

    mock_client = _mock_anthropic_client(_ANALISIS_MOCK, _FLUJO_MOCK)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        gen_resp = client.post("/api/automatizaciones/generar", json={"template_id": tid}, headers=headers)
    aut_id = gen_resp.json()["automatizacion"]["id"]

    resp = client.delete(f"/api/automatizaciones/{aut_id}", headers=headers)
    assert resp.status_code == 204

    resp2 = client.get(f"/api/automatizaciones/{aut_id}", headers=headers)
    assert resp2.status_code == 404


def test_generar_dos_veces_actualiza_no_duplica(client, token_dueno_auto, template_con_pasos_auto):
    """Generar automatización dos veces sobre el mismo template debe actualizar, no duplicar."""
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    tid = template_con_pasos_auto["id"]

    mock_client = _mock_anthropic_client(_ANALISIS_MOCK, _FLUJO_MOCK)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        client.post("/api/automatizaciones/generar", json={"template_id": tid}, headers=headers)

    mock_client2 = _mock_anthropic_client(_ANALISIS_MOCK, _FLUJO_MOCK)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client2):
        client.post("/api/automatizaciones/generar", json={"template_id": tid}, headers=headers)

    resp = client.get("/api/automatizaciones", headers=headers)
    automatizaciones_del_template = [a for a in resp.json() if a["template_id"] == tid]
    assert len(automatizaciones_del_template) == 1


def test_flujo_invalido_retorna_422(client, token_dueno_auto, template_con_pasos_auto):
    """Si Claude genera un flujo sin estructura mínima, debe retornar 422."""
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    tid = template_con_pasos_auto["id"]

    flujo_invalido = {"workflows": [], "version": "1.0"}  # falta nodes, connections, settings
    mock_client = _mock_anthropic_client(_ANALISIS_MOCK, flujo_invalido)
    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        resp = client.post("/api/automatizaciones/generar", json={"template_id": tid}, headers=headers)
    assert resp.status_code == 422


def test_optimizar_descripcion(client, token_dueno_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    template_mock = {
        "nombre": "Proceso de Onboarding",
        "tipo": "onboarding",
        "descripcion": "Incorporación de nuevo cliente",
        "pasos": [
            {"orden": 1, "titulo": "Reunión inicial", "descripcion": "Conocer al cliente", "tiempo_estimado_minutos": 60, "es_automatizable": False}
        ],
    }
    import json
    from unittest.mock import AsyncMock
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(template_mock))]
    mock_client.messages.create = AsyncMock(return_value=mock_msg)

    with patch("services.optimizador_service.anthropic.AsyncAnthropic", return_value=mock_client):
        resp = client.post(
            "/api/procesos/optimizar/desde-descripcion",
            json={"descripcion": "cuando entra un cliente nuevo hay que juntar documentos y explicarles cómo trabajamos"},
            headers=headers,
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "nombre" in data
    assert "pasos" in data


def test_optimizar_descripcion_vacia(client, token_dueno_auto):
    headers = {"Authorization": f"Bearer {token_dueno_auto}"}
    resp = client.post(
        "/api/procesos/optimizar/desde-descripcion",
        json={"descripcion": ""},
        headers=headers,
    )
    assert resp.status_code == 422
