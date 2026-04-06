"""
Tests de tracking de tiempo para tareas (sesiones, iniciar, pausar, completar).
Campos oficiales: horas_estimadas (Float, horas), horas_reales (Float, horas).
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
            "horas_estimadas": 1.0,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


# --- Test 1: iniciar_tarea ---

def test_iniciar_tarea(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    resp = client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "en_progreso"


def test_tarea_creada_con_horas_estimadas(client, auth_headers, tarea_base):
    assert tarea_base["horas_estimadas"] == 1.0
    assert tarea_base["horas_reales"] is None or tarea_base["horas_reales"] == 0


# --- Test 2: iniciar tarea ya activa -> 400 ---

def test_iniciar_tarea_ya_activa(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    assert resp.status_code == 400
    assert "sesión activa" in resp.json()["detail"]


# --- Test 3: pausar tarea ---

def test_pausar_tarea(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "pendiente"
    # horas_reales debe ser > 0 (al menos ~0.016 h = 1 min)
    assert data["horas_reales"] is not None
    assert data["horas_reales"] > 0


def test_pausar_tarea_sin_sesion(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    resp = client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)
    assert resp.status_code == 400


# --- Test 4: completar tarea con sesion ---

def test_completar_tarea_con_sesion(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    resp = client.post(f"/api/tareas/{tid}/completar", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["estado"] == "completada"
    assert data["fecha_completada"] is not None
    assert data["horas_reales"] is not None
    assert data["horas_reales"] > 0


# --- Test 5: completar tarea sin sesion ---

def test_completar_tarea_sin_sesion(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    resp = client.post(f"/api/tareas/{tid}/completar", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["estado"] == "completada"
    # Sin sesion, horas_reales se mantiene en None o 0
    horas = resp.json().get("horas_reales")
    assert horas is None or horas == 0


# --- Test 6: multiples sesiones suman correctamente ---

def test_multiples_sesiones(client, auth_headers, tarea_base):
    tid = tarea_base["id"]

    # Sesion 1
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)

    # Sesion 2
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)
    client.post(f"/api/tareas/{tid}/pausar", headers=auth_headers)

    # Verificar que hay 2 sesiones cerradas
    resp = client.get(f"/api/tareas/{tid}/tiempo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["sesiones"]) == 2
    assert all(s["fin"] is not None for s in data["sesiones"])
    # horas_reales es la suma de ambas (> 0)
    assert data["horas_reales"] is not None
    assert data["horas_reales"] > 0
    assert data["sesion_activa"] is False


# --- Test 7: endpoint GET tiempo ---

def test_endpoint_tiempo(client, auth_headers, tarea_base):
    tid = tarea_base["id"]
    client.post(f"/api/tareas/{tid}/iniciar", headers=auth_headers)

    resp = client.get(f"/api/tareas/{tid}/tiempo", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tarea_id"] == tid
    assert data["horas_estimadas"] == 1.0
    assert "horas_reales" in data
    assert "sesiones" in data
    assert data["sesion_activa"] is True
    assert len(data["sesiones"]) == 1
    assert data["sesiones"][0]["fin"] is None


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
