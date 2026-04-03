"""
Tests de happy path y reglas de negocio del módulo de procesos.
"""
import pytest

from tests.conftest import _crear_token_con_rol


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def template_payload():
    return {"nombre": "Liquidación IVA Mensual", "descripcion": "Proceso mensual", "tipo": "liquidacion_iva"}


@pytest.fixture()
def template_creado(client, auth_headers, template_payload):
    resp = client.post("/api/procesos/templates", json=template_payload, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


@pytest.fixture()
def template_con_pasos(client, auth_headers, template_creado):
    tid = template_creado["id"]
    pasos = [
        {"orden": 1, "titulo": "Recopilar facturas", "descripcion": "Reunir todas las facturas del mes", "tiempo_estimado_minutos": 30, "es_automatizable": False},
        {"orden": 2, "titulo": "Cargar en sistema", "descripcion": "Ingresar datos al sistema contable", "tiempo_estimado_minutos": 60, "es_automatizable": True},
        {"orden": 3, "titulo": "Revisión final", "descripcion": "Verificar totales", "tiempo_estimado_minutos": 20, "es_automatizable": False},
    ]
    for paso in pasos:
        r = client.post(f"/api/procesos/templates/{tid}/pasos", json=paso, headers=auth_headers)
        assert r.status_code == 201
    return template_creado


@pytest.fixture()
def instancia_creada(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    resp = client.post("/api/procesos/instancias", json={"template_id": tid}, headers=auth_headers)
    assert resp.status_code == 201
    return resp.json()


# ─── Templates ────────────────────────────────────────────────────────────────

def test_crear_template(client, auth_headers, template_payload):
    resp = client.post("/api/procesos/templates", json=template_payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["nombre"] == template_payload["nombre"]
    assert data["tipo"] == "liquidacion_iva"
    assert data["sop_generado"] is False
    assert data["pasos"] == []


def test_listar_templates(client, auth_headers, template_creado):
    resp = client.get("/api/procesos/templates", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


def test_obtener_template(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    resp = client.get(f"/api/procesos/templates/{tid}", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["pasos"]) == 3


def test_actualizar_template(client, auth_headers, template_creado):
    tid = template_creado["id"]
    resp = client.put(f"/api/procesos/templates/{tid}", json={"nombre": "IVA Actualizado"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["nombre"] == "IVA Actualizado"


def test_eliminar_template(client, auth_headers, template_creado):
    tid = template_creado["id"]
    resp = client.delete(f"/api/procesos/templates/{tid}", headers=auth_headers)
    assert resp.status_code == 204
    # Ya no aparece en el listado
    lista = client.get("/api/procesos/templates", headers=auth_headers)
    ids = [t["id"] for t in lista.json()]
    assert tid not in ids


def test_template_no_encontrado(client, auth_headers):
    resp = client.get("/api/procesos/templates/99999", headers=auth_headers)
    assert resp.status_code == 404


# ─── Pasos Template ───────────────────────────────────────────────────────────

def test_agregar_paso(client, auth_headers, template_creado):
    tid = template_creado["id"]
    resp = client.post(
        f"/api/procesos/templates/{tid}/pasos",
        json={"orden": 1, "titulo": "Paso inicial", "tiempo_estimado_minutos": 15},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["orden"] == 1


def test_orden_duplicado_rechazado(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    resp = client.post(
        f"/api/procesos/templates/{tid}/pasos",
        json={"orden": 1, "titulo": "Duplicado"},
        headers=auth_headers,
    )
    assert resp.status_code == 409


def test_actualizar_paso(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    pasos = client.get(f"/api/procesos/templates/{tid}", headers=auth_headers).json()["pasos"]
    paso_id = pasos[0]["id"]
    resp = client.put(f"/api/procesos/pasos-template/{paso_id}", json={"titulo": "Paso modificado"}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["titulo"] == "Paso modificado"


def test_eliminar_paso_renumera(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    pasos = client.get(f"/api/procesos/templates/{tid}", headers=auth_headers).json()["pasos"]
    # Eliminar el paso 1
    paso1_id = next(p["id"] for p in pasos if p["orden"] == 1)
    resp = client.delete(f"/api/procesos/pasos-template/{paso1_id}", headers=auth_headers)
    assert resp.status_code == 204
    # Verificar que los pasos restantes se renumeraron
    pasos_actualizados = client.get(f"/api/procesos/templates/{tid}", headers=auth_headers).json()["pasos"]
    ordenes = [p["orden"] for p in pasos_actualizados]
    assert ordenes == [1, 2]


# ─── Instancias ───────────────────────────────────────────────────────────────

def test_crear_instancia_copia_pasos(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    resp = client.post("/api/procesos/instancias", json={"template_id": tid}, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["estado"] == "pendiente"
    assert data["progreso_pct"] == 0.0
    assert len(data["pasos"]) == 3


def test_instancia_con_cliente_invalido(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    resp = client.post(
        "/api/procesos/instancias",
        json={"template_id": tid, "cliente_id": 99999},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ─── Avanzar pasos (secuencialidad + progreso) ───────────────────────────────

def test_secuencialidad_bloquea_paso_2_sin_completar_paso_1(client, auth_headers, instancia_creada):
    pasos = instancia_creada["pasos"]
    paso2_id = next(p["id"] for p in pasos if p["orden"] == 2)
    resp = client.put(
        f"/api/procesos/pasos-instancia/{paso2_id}",
        json={"estado": "en_progreso"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_avanzar_paso_1_en_progreso(client, auth_headers, instancia_creada):
    pasos = instancia_creada["pasos"]
    paso1_id = next(p["id"] for p in pasos if p["orden"] == 1)
    resp = client.put(
        f"/api/procesos/pasos-instancia/{paso1_id}",
        json={"estado": "en_progreso"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["estado"] == "en_progreso"
    assert resp.json()["fecha_inicio"] is not None


def test_completar_paso_1_permite_paso_2(client, auth_headers, instancia_creada):
    pasos = instancia_creada["pasos"]
    paso1_id = next(p["id"] for p in pasos if p["orden"] == 1)
    # Primero en_progreso
    client.put(f"/api/procesos/pasos-instancia/{paso1_id}", json={"estado": "en_progreso"}, headers=auth_headers)
    # Luego completado
    client.put(f"/api/procesos/pasos-instancia/{paso1_id}", json={"estado": "completado"}, headers=auth_headers)
    # Ahora paso 2 puede avanzar
    paso2_id = next(p["id"] for p in pasos if p["orden"] == 2)
    resp = client.put(
        f"/api/procesos/pasos-instancia/{paso2_id}",
        json={"estado": "en_progreso"},
        headers=auth_headers,
    )
    assert resp.status_code == 200


def test_progreso_recalculado(client, auth_headers, instancia_creada):
    inst_id = instancia_creada["id"]
    pasos = instancia_creada["pasos"]
    paso1_id = next(p["id"] for p in pasos if p["orden"] == 1)
    # Completar paso 1
    client.put(f"/api/procesos/pasos-instancia/{paso1_id}", json={"estado": "en_progreso"}, headers=auth_headers)
    client.put(f"/api/procesos/pasos-instancia/{paso1_id}", json={"estado": "completado"}, headers=auth_headers)
    # Verificar progreso
    resp = client.get(f"/api/procesos/instancias/{inst_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert abs(resp.json()["progreso_pct"] - (1 / 3)) < 0.01


def test_completar_todos_pasos_completa_instancia(client, auth_headers, instancia_creada):
    inst_id = instancia_creada["id"]
    pasos = sorted(instancia_creada["pasos"], key=lambda p: p["orden"])
    for paso in pasos:
        client.put(f"/api/procesos/pasos-instancia/{paso['id']}", json={"estado": "en_progreso"}, headers=auth_headers)
        client.put(f"/api/procesos/pasos-instancia/{paso['id']}", json={"estado": "completado"}, headers=auth_headers)
    resp = client.get(f"/api/procesos/instancias/{inst_id}", headers=auth_headers)
    data = resp.json()
    assert data["estado"] == "completado"
    assert data["progreso_pct"] == 1.0
    assert data["fecha_fin"] is not None


def test_tiempo_real_calculado_al_completar(client, auth_headers, instancia_creada):
    pasos = instancia_creada["pasos"]
    paso1_id = next(p["id"] for p in pasos if p["orden"] == 1)
    # en_progreso registra fecha_inicio
    r1 = client.put(f"/api/procesos/pasos-instancia/{paso1_id}", json={"estado": "en_progreso"}, headers=auth_headers)
    assert r1.json()["fecha_inicio"] is not None
    # completar calcula tiempo_real_minutos
    r2 = client.put(f"/api/procesos/pasos-instancia/{paso1_id}", json={"estado": "completado"}, headers=auth_headers)
    assert r2.json()["tiempo_real_minutos"] is not None
    assert r2.json()["tiempo_real_minutos"] >= 0


# ─── SOP ──────────────────────────────────────────────────────────────────────

def test_generar_sop(client, auth_headers, template_con_pasos):
    tid = template_con_pasos["id"]
    resp = client.post(f"/api/procesos/templates/{tid}/sop", headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert "sop_url" in data
    assert f"sop_{tid}_v1.pdf" in data["sop_url"]
    # El template refleja la URL
    template_resp = client.get(f"/api/procesos/templates/{tid}", headers=auth_headers)
    assert template_resp.json()["sop_generado"] is True


def test_conocimiento_sops_solo_con_sop(client, auth_headers):
    # Crear template SIN pasos (no tendrá SOP)
    r1 = client.post(
        "/api/procesos/templates",
        json={"nombre": "Sin SOP", "tipo": "otro"},
        headers=auth_headers,
    )
    assert r1.status_code == 201
    tid_sin_sop = r1.json()["id"]

    # Crear template CON pasos y generar SOP
    r2 = client.post(
        "/api/procesos/templates",
        json={"nombre": "Con SOP", "tipo": "balance"},
        headers=auth_headers,
    )
    assert r2.status_code == 201
    tid_con_sop = r2.json()["id"]
    client.post(
        f"/api/procesos/templates/{tid_con_sop}/pasos",
        json={"orden": 1, "titulo": "Paso único"},
        headers=auth_headers,
    )
    sop_resp = client.post(f"/api/procesos/templates/{tid_con_sop}/sop", headers=auth_headers)
    assert sop_resp.status_code == 201

    resp = client.get("/api/conocimiento/sops", headers=auth_headers)
    assert resp.status_code == 200
    ids_con_sop = [t["id"] for t in resp.json()]
    assert tid_con_sop in ids_con_sop
    assert tid_sin_sop not in ids_con_sop
