"""
Tests de tracking de tiempo para tareas (sesiones, iniciar, pausar, completar).
"""
import pytest

from tests.conftest import _crear_token_con_rol


@pytest.fixture()
def tarea_base(client, db, auth_headers, cliente_test):
    resp = client.post(
        "/api/tareas",
        json={
            "cliente_id": cliente_test.id,
            "titulo": "Tarea de prueba tiempo",
            "tipo": "tarea",
            "tiempo_estimado_min": 60,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


# ─── Test 1: iniciar_tarea ────────────────────────────────────────────────────

def test_iniciar_tarea(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    resp = client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "en_progreso"


def test_tarea_creada_con_tiempo_estimado(client, auth_headers, tarea_base):
    assert tarea_base["tiempo_estimado_min"] == 60
    assert tarea_base["tiempo_real_min"] == 0


# ─── Test 2: iniciar tarea ya activa → 400 ───────────────────────────────────

def test_iniciar_tarea_ya_activa(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    assert resp.status_code == 400
    assert "sesión activa" in resp.json()["detail"]


# ─── Test 3: pausar tarea ────────────────────────────────────────────────────

def test_pausar_tarea(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "pendiente"
    # tiempo_real_min debe ser al menos 1 minuto (mínimo garantizado)
    assert data["tiempo_real_min"] >= 1


def test_pausar_tarea_sin_sesion(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    resp = client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)
    assert resp.status_code == 400


# ─── Test 4: completar tarea con sesión ──────────────────────────────────────

def test_completar_tarea_con_sesion(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/completar", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "completada"
    assert data["fecha_completada"] is not None
    assert data["tiempo_real_min"] >= 1


# ─── Test 5: completar tarea sin sesión ──────────────────────────────────────

def test_completar_tarea_sin_sesion(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    # No iniciar — completar directamente
    resp = client.post(f"/api/tareas/{tid}/completar", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["estado"] == "completada"
    # Sin sesión, tiempo_real_min se mantiene en 0
    assert resp.json()["tiempo_real_min"] == 0


# ─── Test 6: múltiples sesiones suman correctamente ──────────────────────────

def test_multiples_sesiones(client, auth_headers, tarea_base):
    tid = tarea_base["id"]

    # Sesión 1
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)

    # Sesión 2
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)

    # Verificar que hay 2 sesiones cerradas
    resp = client.get(f"/api/tareas/{tid}/tiempo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sesiones"]) == 2
    # Ambas sesiones cerradas
    assert all(s["fin"] is not None for s in data["sesiones"])
    # tiempo_real_min es la suma de ambas (>= 2 por mínimo de 1 por sesión)
    assert data["tiempo_real_min"] >= 2
    assert data["sesion_activa"] is False


# ─── Test 7: endpoint GET tiempo ─────────────────────────────────────────────

def test_endpoint_tiempo(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)

    resp = client.get(f"/api/tareas/{tid}/tiempo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tarea_id"] == tid
    assert data["tiempo_estimado_min"] == 60
    assert "tiempo_real_min" in data
    assert "sesiones" in data
    assert data["sesion_activa"] is True
    assert len(data["sesiones"]) == 1
    assert data["sesiones"][0]["fin"] is None  # sesión aún abierta


def test_completar_tarea_ya_completada(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/completar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/completar", headers=auth_headers)
    assert resp.status_code == 400


def test_iniciar_tarea_completada(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/completar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    assert resp.status_code == 400
