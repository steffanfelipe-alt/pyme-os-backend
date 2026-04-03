"""
Tests de RBAC para el módulo de procesos.
Verifica permisos por rol según la tabla del plan.
"""
import pytest

from tests.conftest import _crear_token_con_rol


@pytest.fixture()
def template_dueno(client, db):
    token = _crear_token_con_rol(db, "dueno_rbac@pymeos.com", "Dueño RBAC", "dueno")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso RBAC", "tipo": "onboarding"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json(), token, headers


@pytest.fixture()
def template_contador(client, db):
    token = _crear_token_con_rol(db, "contador_rbac@pymeos.com", "Contador RBAC", "contador")
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso Contador", "tipo": "liquidacion_iva"},
        headers=headers,
    )
    assert resp.status_code == 201
    return resp.json(), token, headers


# ─── Creación de templates ────────────────────────────────────────────────────

def test_contador_puede_crear_template(client, db):
    token = _crear_token_con_rol(db, "c1@pymeos.com", "Contador", "contador")
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso Contador", "tipo": "balance"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


def test_administrativo_no_puede_crear_template(client, db):
    token = _crear_token_con_rol(db, "admin_rbac@pymeos.com", "Admin RBAC", "administrativo")
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso Admin", "tipo": "otro"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_rrhh_no_puede_crear_template(client, db):
    token = _crear_token_con_rol(db, "rrhh_rbac@pymeos.com", "RRHH RBAC", "rrhh")
    resp = client.post(
        "/api/procesos/templates",
        json={"nombre": "Proceso RRHH", "tipo": "otro"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_rrhh_no_puede_ver_templates(client, db):
    token = _crear_token_con_rol(db, "rrhh2_rbac@pymeos.com", "RRHH2 RBAC", "rrhh")
    resp = client.get(
        "/api/procesos/templates",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ─── Edición de templates ────────────────────────────────────────────────────

def test_dueno_puede_editar_cualquier_template(client, db, template_contador):
    template, _, _ = template_contador
    token_dueno = _crear_token_con_rol(db, "dueno_edit@pymeos.com", "Dueño Edit", "dueno")
    resp = client.put(
        f"/api/procesos/templates/{template['id']}",
        json={"nombre": "Editado por dueño"},
        headers={"Authorization": f"Bearer {token_dueno}"},
    )
    assert resp.status_code == 200
    assert resp.json()["nombre"] == "Editado por dueño"


def test_contador_puede_editar_sus_propios_templates(client, db, template_contador):
    template, token_contador, headers_contador = template_contador
    resp = client.put(
        f"/api/procesos/templates/{template['id']}",
        json={"nombre": "Editado por su contador"},
        headers=headers_contador,
    )
    assert resp.status_code == 200


def test_contador_no_puede_editar_template_ajeno(client, db, template_dueno):
    template, _, _ = template_dueno
    token_otro_contador = _crear_token_con_rol(db, "otro_contador@pymeos.com", "Otro Contador", "contador")
    resp = client.put(
        f"/api/procesos/templates/{template['id']}",
        json={"nombre": "Intento fallido"},
        headers={"Authorization": f"Bearer {token_otro_contador}"},
    )
    assert resp.status_code == 403


# ─── Eliminación de templates ────────────────────────────────────────────────

def test_solo_dueno_puede_eliminar_template(client, db, template_dueno):
    template, token_dueno, headers_dueno = template_dueno
    resp = client.delete(f"/api/procesos/templates/{template['id']}", headers=headers_dueno)
    assert resp.status_code == 204


def test_contador_no_puede_eliminar_template(client, db, template_contador):
    template, token_contador, headers_contador = template_contador
    resp = client.delete(f"/api/procesos/templates/{template['id']}", headers=headers_contador)
    assert resp.status_code == 403


# ─── Instancias ───────────────────────────────────────────────────────────────

def test_administrativo_puede_instanciar(client, db, template_dueno):
    template, _, _ = template_dueno
    token_admin = _crear_token_con_rol(db, "admin_inst@pymeos.com", "Admin Inst", "administrativo")
    resp = client.post(
        "/api/procesos/instancias",
        json={"template_id": template["id"]},
        headers={"Authorization": f"Bearer {token_admin}"},
    )
    assert resp.status_code == 201


def test_rrhh_no_puede_instanciar(client, db, template_dueno):
    template, _, _ = template_dueno
    token_rrhh = _crear_token_con_rol(db, "rrhh_inst@pymeos.com", "RRHH Inst", "rrhh")
    resp = client.post(
        "/api/procesos/instancias",
        json={"template_id": template["id"]},
        headers={"Authorization": f"Bearer {token_rrhh}"},
    )
    assert resp.status_code == 403


# ─── Automatizaciones (solo_dueno) ───────────────────────────────────────────

def test_contador_no_puede_ver_automatizaciones(client, db):
    token = _crear_token_con_rol(db, "cont_auto@pymeos.com", "Cont Auto", "contador")
    resp = client.get("/api/automatizaciones", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_administrativo_no_puede_ver_automatizaciones(client, db):
    token = _crear_token_con_rol(db, "admin_auto@pymeos.com", "Admin Auto", "administrativo")
    resp = client.get("/api/automatizaciones", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_dueno_puede_ver_automatizaciones(client, db):
    token = _crear_token_con_rol(db, "dueno_auto@pymeos.com", "Dueño Auto", "dueno")
    resp = client.get("/api/automatizaciones", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
