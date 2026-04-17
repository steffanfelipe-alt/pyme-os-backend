"""Tests — D1 Matriz Eisenhower"""
import pytest
from tests.conftest import _crear_token_con_rol
from models.tarea import Tarea, TipoTarea, EstadoTarea, PrioridadTarea
from models.cliente import Cliente, TipoPersona, CondicionFiscal
from models.empleado import Empleado, RolEmpleado
from models.studio import Studio


# ── helpers ──────────────────────────────────────────────────────────────────

def _studio(db):
    s = Studio(nombre="Test Studio")
    db.add(s)
    db.flush()
    return s


def _empleado(db, studio_id, email="emp@test.com"):
    e = Empleado(nombre="Emp", email=email, rol=RolEmpleado.contador, activo=True, studio_id=studio_id)
    db.add(e)
    db.flush()
    return e


def _tarea(db, studio_id, urgente=False, importante=False, estado=EstadoTarea.pendiente, empleado_id=None):
    t = Tarea(
        studio_id=studio_id,
        titulo="Tarea test",
        tipo=TipoTarea.otro,
        prioridad=PrioridadTarea.normal,
        estado=estado,
        es_urgente=urgente,
        es_importante=importante,
        activo=True,
        empleado_id=empleado_id,
    )
    db.add(t)
    db.flush()
    return t


def _token(db, studio_id):
    from models.usuario import Usuario
    from auth import hash_password, create_access_token
    u = Usuario(email="dueno@e.com", password_hash=hash_password("pass"), nombre="D", studio_id=studio_id)
    db.add(u)
    db.flush()
    e = _empleado(db, studio_id, email="dueno@e.com")
    db.commit()
    return create_access_token({"sub": str(u.id), "email": u.email, "rol": "dueno",
                                 "empleado_id": e.id, "studio_id": studio_id})


# ── tests ─────────────────────────────────────────────────────────────────────

def test_patch_prioridad_ok(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    t = _tarea(db, s.id)
    db.commit()

    r = client.patch(f"/api/tareas/{t.id}/prioridad",
                     json={"es_urgente": True, "es_importante": True},
                     headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert data["es_urgente"] is True
    assert data["es_importante"] is True


def test_patch_prioridad_tarea_no_existe(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    db.commit()

    r = client.patch("/api/tareas/99999/prioridad",
                     json={"es_urgente": True, "es_importante": False},
                     headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 404


def test_patch_prioridad_tarea_otro_studio(client, db):
    s1 = _studio(db)
    s2 = Studio(nombre="Otro Studio"); db.add(s2); db.flush()
    tok1 = _token(db, s1.id)
    t = _tarea(db, s2.id)
    db.commit()

    r = client.patch(f"/api/tareas/{t.id}/prioridad",
                     json={"es_urgente": True, "es_importante": True},
                     headers={"Authorization": f"Bearer {tok1}"})
    assert r.status_code == 404  # studio isolation → 404


def test_get_matriz_vacia(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    db.commit()

    r = client.get("/api/tareas/matriz-eisenhower",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    for key in ("q1_urgente_importante", "q2_no_urgente_importante",
                "q3_urgente_no_importante", "q4_no_urgente_no_importante", "sin_clasificar"):
        assert data[key] == []


def test_get_matriz_clasifica_q1(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    _tarea(db, s.id, urgente=True, importante=True)
    db.commit()

    r = client.get("/api/tareas/matriz-eisenhower",
                   headers={"Authorization": f"Bearer {tok}"})
    data = r.json()
    assert len(data["q1_urgente_importante"]) == 1
    assert data["q2_no_urgente_importante"] == []


def test_get_matriz_clasifica_q2(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    _tarea(db, s.id, urgente=False, importante=True)
    db.commit()

    r = client.get("/api/tareas/matriz-eisenhower",
                   headers={"Authorization": f"Bearer {tok}"})
    data = r.json()
    assert len(data["q2_no_urgente_importante"]) == 1


def test_get_matriz_clasifica_q3(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    _tarea(db, s.id, urgente=True, importante=False)
    db.commit()

    r = client.get("/api/tareas/matriz-eisenhower",
                   headers={"Authorization": f"Bearer {tok}"})
    data = r.json()
    assert len(data["q3_urgente_no_importante"]) == 1


def test_get_matriz_sin_clasificar_cuando_ambos_false(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    _tarea(db, s.id, urgente=False, importante=False)
    db.commit()

    r = client.get("/api/tareas/matriz-eisenhower",
                   headers={"Authorization": f"Bearer {tok}"})
    data = r.json()
    assert len(data["sin_clasificar"]) == 1
    assert data["q4_no_urgente_no_importante"] == []


def test_get_matriz_filtro_por_empleado_id(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    emp = _empleado(db, s.id, email="emp2@test.com")
    _tarea(db, s.id, urgente=True, importante=True, empleado_id=emp.id)
    _tarea(db, s.id, urgente=True, importante=True)  # sin empleado
    db.commit()

    r = client.get(f"/api/tareas/matriz-eisenhower?empleado_id={emp.id}",
                   headers={"Authorization": f"Bearer {tok}"})
    data = r.json()
    assert len(data["q1_urgente_importante"]) == 1


def test_get_matriz_excluye_tareas_completadas(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    _tarea(db, s.id, urgente=True, importante=True, estado=EstadoTarea.completada)
    db.commit()

    r = client.get("/api/tareas/matriz-eisenhower",
                   headers={"Authorization": f"Bearer {tok}"})
    data = r.json()
    assert data["q1_urgente_importante"] == []
