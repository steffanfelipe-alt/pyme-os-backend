"""Tests E1 — Portal tareas delegadas al cliente."""
import pytest
from models.portal_token import PortalToken
from models.tarea import EstadoTarea, PrioridadTarea, Tarea, TipoTarea


def _crear_tarea(db, cliente_id, studio_id, titulo="Tarea test", estado=EstadoTarea.pendiente):
    t = Tarea(
        studio_id=studio_id,
        cliente_id=cliente_id,
        titulo=titulo,
        tipo=TipoTarea.otro,
        prioridad=PrioridadTarea.normal,
        estado=estado,
        activo=True,
    )
    db.add(t)
    db.commit()
    return t


# ── Generación de token ───────────────────────────────────────────────────────

def test_generar_token_exitoso(client, auth_headers, db, cliente_test):
    r = client.post(f"/api/portal/tokens?cliente_id={cliente_test.id}", headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert "token" in data
    assert data["cliente_id"] == cliente_test.id
    assert data["activo"] is True
    assert data["expira_at"] is not None


def test_generar_token_cliente_inexistente(client, auth_headers):
    r = client.post("/api/portal/tokens?cliente_id=99999", headers=auth_headers)
    assert r.status_code == 404


def test_generar_token_revoca_anterior(client, auth_headers, db, cliente_test):
    r1 = client.post(f"/api/portal/tokens?cliente_id={cliente_test.id}", headers=auth_headers)
    token1 = r1.json()["token"]
    r2 = client.post(f"/api/portal/tokens?cliente_id={cliente_test.id}", headers=auth_headers)
    token2 = r2.json()["token"]

    assert token1 != token2

    # El token anterior ya no es activo en DB
    old = db.query(PortalToken).filter(PortalToken.token == token1).first()
    assert old is not None
    assert old.activo is False


def test_generar_token_requiere_auth(client, cliente_test):
    r = client.post(f"/api/portal/tokens?cliente_id={cliente_test.id}")
    assert r.status_code == 401 or r.status_code == 403


# ── Consulta pública de tareas ────────────────────────────────────────────────

def test_portal_obtener_tareas(client, auth_headers, db, cliente_test):
    _crear_tarea(db, cliente_test.id, cliente_test.studio_id, "Hacer declaración", EstadoTarea.pendiente)
    _crear_tarea(db, cliente_test.id, cliente_test.studio_id, "Revisar facturas", EstadoTarea.completada)

    gen = client.post(f"/api/portal/tokens?cliente_id={cliente_test.id}", headers=auth_headers)
    token = gen.json()["token"]

    r = client.get(f"/api/portal/cliente/{token}/tareas")
    assert r.status_code == 200
    data = r.json()
    assert data["cliente_nombre"] == cliente_test.nombre
    assert len(data["tareas"]) == 2
    assert data["pendientes"] == 1
    assert data["completadas"] == 1


def test_portal_token_invalido(client):
    r = client.get("/api/portal/cliente/token_invalido_xyz/tareas")
    assert r.status_code == 404


def test_portal_no_muestra_tareas_de_otro_cliente(client, auth_headers, db, cliente_test):
    from models.cliente import Cliente, TipoPersona, CondicionFiscal
    from tests.conftest import _get_or_create_studio

    studio_id = _get_or_create_studio(db)
    otro_cliente = Cliente(
        studio_id=studio_id,
        tipo_persona=TipoPersona.fisica,
        nombre="Otro Cliente",
        cuit_cuil="23-12345678-5",
        condicion_fiscal=CondicionFiscal.monotributista,
        activo=True,
    )
    db.add(otro_cliente)
    db.commit()
    db.refresh(otro_cliente)

    _crear_tarea(db, otro_cliente.id, studio_id, "Tarea de otro", EstadoTarea.pendiente)

    gen = client.post(f"/api/portal/tokens?cliente_id={cliente_test.id}", headers=auth_headers)
    token = gen.json()["token"]

    r = client.get(f"/api/portal/cliente/{token}/tareas")
    assert r.status_code == 200
    tareas = r.json()["tareas"]
    titulos = [t["titulo"] for t in tareas]
    assert "Tarea de otro" not in titulos


# ── Revocación ────────────────────────────────────────────────────────────────

def test_revocar_token(client, auth_headers, db, cliente_test):
    gen = client.post(f"/api/portal/tokens?cliente_id={cliente_test.id}", headers=auth_headers)
    token = gen.json()["token"]

    rev = client.delete(f"/api/portal/tokens/{cliente_test.id}", headers=auth_headers)
    assert rev.status_code == 200
    assert rev.json()["revocados"] == 1

    # Token ya no sirve
    r = client.get(f"/api/portal/cliente/{token}/tareas")
    assert r.status_code == 404
