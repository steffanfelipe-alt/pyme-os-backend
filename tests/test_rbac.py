"""
Tests de RBAC — verifica que cada rol accede solo a lo que le corresponde.
"""
import pytest
from fastapi.testclient import TestClient

from auth import create_access_token, hash_password
from models.cliente import Cliente, CondicionFiscal, TipoPersona
from models.empleado import Empleado, RolEmpleado
from models.usuario import Usuario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _crear_cliente(db, nombre: str, cuit: str, contador_id: int | None = None) -> Cliente:
    cliente = Cliente(
        tipo_persona=TipoPersona.juridica,
        nombre=nombre,
        cuit_cuil=cuit,
        condicion_fiscal=CondicionFiscal.responsable_inscripto,
        activo=True,
        contador_asignado_id=contador_id,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


# ---------------------------------------------------------------------------
# test_token_incluye_rol
# ---------------------------------------------------------------------------

def test_token_incluye_rol(token_dueno):
    """El JWT generado con rol dueno contiene el campo 'rol'."""
    from jose import jwt
    import os
    payload = jwt.decode(token_dueno, os.environ["SECRET_KEY"], algorithms=["HS256"])
    assert payload.get("rol") == "dueno"
    assert payload.get("empleado_id") is not None


# ---------------------------------------------------------------------------
# test_dueno_ve_todos_los_clientes
# ---------------------------------------------------------------------------

def test_dueno_ve_todos_los_clientes(client, db, token_dueno):
    """El dueño recibe todos los clientes del studio."""
    # Crear 2 empleados-contadores
    emp1 = Empleado(nombre="C1", email="c1@test.com", rol=RolEmpleado.contador, activo=True)
    emp2 = Empleado(nombre="C2", email="c2@test.com", rol=RolEmpleado.contador, activo=True)
    db.add_all([emp1, emp2])
    db.flush()

    _crear_cliente(db, "Cliente A", "20-11111111-1", emp1.id)
    _crear_cliente(db, "Cliente B", "20-22222222-2", emp2.id)
    _crear_cliente(db, "Cliente C", "20-33333333-3", None)

    resp = client.get("/api/clientes", headers=_headers(token_dueno))
    assert resp.status_code == 200
    assert len(resp.json()) == 3


# ---------------------------------------------------------------------------
# test_contador_solo_ve_sus_clientes
# ---------------------------------------------------------------------------

def test_contador_solo_ve_sus_clientes(client, db, token_contador):
    """Un contador solo ve los clientes donde contador_asignado_id coincide con su empleado_id."""
    from jose import jwt
    import os
    payload = jwt.decode(token_contador, os.environ["SECRET_KEY"], algorithms=["HS256"])
    mi_empleado_id = payload["empleado_id"]

    # Otro contador
    otro = Empleado(nombre="Otro", email="otro@test.com", rol=RolEmpleado.contador, activo=True)
    db.add(otro)
    db.flush()

    # 2 clientes asignados al contador logueado, 3 del otro
    _crear_cliente(db, "Mio A", "20-10000001-1", mi_empleado_id)
    _crear_cliente(db, "Mio B", "20-10000002-2", mi_empleado_id)
    _crear_cliente(db, "Ajeno A", "20-20000001-1", otro.id)
    _crear_cliente(db, "Ajeno B", "20-20000002-2", otro.id)
    _crear_cliente(db, "Ajeno C", "20-20000003-3", otro.id)

    resp = client.get("/api/clientes", headers=_headers(token_contador))
    assert resp.status_code == 200
    nombres = {c["nombre"] for c in resp.json()}
    assert nombres == {"Mio A", "Mio B"}


# ---------------------------------------------------------------------------
# test_contador_no_accede_reportes
# ---------------------------------------------------------------------------

def test_contador_no_accede_reportes(client, token_contador):
    """GET /api/reports con rol contador devuelve 403."""
    resp = client.get("/api/reports/", headers=_headers(token_contador))
    assert resp.status_code == 403


def test_contador_no_accede_profitability(client, token_contador):
    """GET /api/profitability con rol contador devuelve 403."""
    resp = client.get("/api/profitability/clients?periodo=2026-03", headers=_headers(token_contador))
    assert resp.status_code == 403


def test_workload_eliminado(client, token_contador):
    """El módulo workload fue eliminado en v2 — el endpoint retorna 404."""
    resp = client.get("/api/workload/team", headers=_headers(token_contador))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# test_rrhh_no_accede_clientes
# ---------------------------------------------------------------------------

def test_rrhh_no_accede_clientes(client, token_rrhh):
    """GET /api/clientes con rol rrhh devuelve 403."""
    resp = client.get("/api/clientes", headers=_headers(token_rrhh))
    assert resp.status_code == 403


def test_rrhh_accede_empleados(client, db, token_rrhh):
    """RRHH puede listar empleados."""
    resp = client.get("/api/empleados", headers=_headers(token_rrhh))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# test_administrativo_no_puede_eliminar
# ---------------------------------------------------------------------------

def test_administrativo_no_puede_eliminar_cliente(client, db, token_administrativo):
    """DELETE /api/clientes/{id} con rol administrativo devuelve 403."""
    cliente = _crear_cliente(db, "Para borrar", "20-99999999-9")
    resp = client.delete(f"/api/clientes/{cliente.id}", headers=_headers(token_administrativo))
    assert resp.status_code == 403


def test_administrativo_no_puede_eliminar_tarea(client, db, token_administrativo, cliente_test):
    """DELETE /api/tareas/{id} con rol administrativo devuelve 403."""
    from models.tarea import EstadoTarea, PrioridadTarea, Tarea, TipoTarea
    tarea = Tarea(
        titulo="T1",
        tipo=TipoTarea.tarea,
        cliente_id=cliente_test.id,
        estado=EstadoTarea.pendiente,
        prioridad=PrioridadTarea.media,
        activo=True,
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)
    resp = client.delete(f"/api/tareas/{tarea.id}", headers=_headers(token_administrativo))
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# test_contador_no_ve_clientes_de_otro_contador
# ---------------------------------------------------------------------------

def test_contador_no_accede_cliente_ajeno(client, db, token_contador):
    """Un contador no puede obtener el detalle de un cliente no asignado a él (403)."""
    otro = Empleado(nombre="Otro2", email="otro2@test.com", rol=RolEmpleado.contador, activo=True)
    db.add(otro)
    db.flush()
    cliente_ajeno = _crear_cliente(db, "Ajeno", "20-55555555-5", otro.id)

    resp = client.get(f"/api/clientes/{cliente_ajeno.id}", headers=_headers(token_contador))
    assert resp.status_code == 403
