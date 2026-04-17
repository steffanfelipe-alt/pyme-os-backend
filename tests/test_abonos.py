"""Tests F1 + F2 — Abonos y cobros."""
from datetime import date, timedelta

import pytest
from models.abono import Abono, Cobro, EstadoCobro


def _hoy() -> str:
    return date.today().isoformat()


def _ayer() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def _crear_abono(client, auth_headers, cliente_id, monto=1000.0, concepto="Honorarios", periodicidad="mensual"):
    return client.post("/api/abonos", json={
        "cliente_id": cliente_id,
        "concepto": concepto,
        "monto": monto,
        "periodicidad": periodicidad,
        "fecha_inicio": _hoy(),
    }, headers=auth_headers)


# ── F1: Abonos CRUD ───────────────────────────────────────────────────────────

def test_crear_abono(client, auth_headers, cliente_test):
    r = _crear_abono(client, auth_headers, cliente_test.id)
    assert r.status_code == 201
    data = r.json()
    assert data["monto"] == 1000.0
    assert data["periodicidad"] == "mensual"
    assert data["fecha_proximo_cobro"] is not None
    assert data["activo"] is True


def test_crear_abono_cliente_inexistente(client, auth_headers):
    r = client.post("/api/abonos", json={
        "cliente_id": 99999,
        "concepto": "Test",
        "monto": 500.0,
        "periodicidad": "mensual",
        "fecha_inicio": _hoy(),
    }, headers=auth_headers)
    assert r.status_code == 404


def test_listar_abonos_vacio(client, auth_headers):
    r = client.get("/api/abonos", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []


def test_listar_abonos(client, auth_headers, cliente_test):
    _crear_abono(client, auth_headers, cliente_test.id, concepto="Asesoramiento")
    _crear_abono(client, auth_headers, cliente_test.id, concepto="Liquidaciones")

    r = client.get("/api/abonos", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_listar_abonos_por_cliente(client, auth_headers, db, cliente_test):
    from models.cliente import Cliente, TipoPersona, CondicionFiscal
    from tests.conftest import _get_or_create_studio

    studio_id = _get_or_create_studio(db)
    otro = Cliente(
        studio_id=studio_id, tipo_persona=TipoPersona.fisica,
        nombre="Otro", cuit_cuil="23-12345678-5",
        condicion_fiscal=CondicionFiscal.monotributista, activo=True,
    )
    db.add(otro)
    db.commit()
    db.refresh(otro)

    _crear_abono(client, auth_headers, cliente_test.id, concepto="A")
    _crear_abono(client, auth_headers, otro.id, concepto="B")

    r = client.get(f"/api/abonos?cliente_id={cliente_test.id}", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["concepto"] == "A"


def test_obtener_abono(client, auth_headers, cliente_test):
    cr = _crear_abono(client, auth_headers, cliente_test.id)
    abono_id = cr.json()["id"]

    r = client.get(f"/api/abonos/{abono_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["id"] == abono_id


def test_obtener_abono_404(client, auth_headers):
    r = client.get("/api/abonos/99999", headers=auth_headers)
    assert r.status_code == 404


def test_actualizar_abono(client, auth_headers, cliente_test):
    cr = _crear_abono(client, auth_headers, cliente_test.id)
    abono_id = cr.json()["id"]

    r = client.put(f"/api/abonos/{abono_id}", json={"concepto": "Nuevo concepto", "monto": 2000.0}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["concepto"] == "Nuevo concepto"
    assert data["monto"] == 2000.0


def test_crear_abono_genera_primer_cobro(client, auth_headers, db, cliente_test):
    cr = _crear_abono(client, auth_headers, cliente_test.id)
    abono_id = cr.json()["id"]

    # Debe existir al menos un cobro pendiente
    cobros = db.query(Cobro).filter(Cobro.abono_id == abono_id).all()
    assert len(cobros) == 1
    assert cobros[0].estado == EstadoCobro.pendiente


# ── Cobros ────────────────────────────────────────────────────────────────────

def test_listar_cobros_abono(client, auth_headers, cliente_test):
    cr = _crear_abono(client, auth_headers, cliente_test.id)
    abono_id = cr.json()["id"]

    r = client.get(f"/api/abonos/{abono_id}/cobros", headers=auth_headers)
    assert r.status_code == 200
    cobros = r.json()
    assert len(cobros) == 1
    assert cobros[0]["estado"] == "pendiente"


def test_registrar_pago_genera_siguiente_cobro(client, auth_headers, db, cliente_test):
    cr = _crear_abono(client, auth_headers, cliente_test.id)
    abono_id = cr.json()["id"]

    cobros_antes = db.query(Cobro).filter(Cobro.abono_id == abono_id).all()
    cobro_id = cobros_antes[0].id

    r = client.patch(f"/api/abonos/{abono_id}/cobros/{cobro_id}/pagar", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["estado"] == "cobrado"

    # Debe haber un nuevo cobro pendiente
    cobros_despues = db.query(Cobro).filter(Cobro.abono_id == abono_id).all()
    assert len(cobros_despues) == 2
    nuevo = next(c for c in cobros_despues if c.estado == EstadoCobro.pendiente)
    assert nuevo is not None


def test_cobros_pendientes(client, auth_headers, cliente_test):
    _crear_abono(client, auth_headers, cliente_test.id)
    r = client.get("/api/abonos/cobros/pendientes", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_resumen_cobros(client, auth_headers, cliente_test):
    _crear_abono(client, auth_headers, cliente_test.id, monto=500.0)
    r = client.get("/api/abonos/cobros/resumen", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "pendientes" in data
    assert "cobrados" in data
    assert "vencidos" in data
    assert "monto_pendiente" in data


# ── F2: Evaluación de cobros vencidos ────────────────────────────────────────

def test_evaluar_cobros_vencidos(client, auth_headers, db, cliente_test):
    """Cobros con fecha_cobro en el pasado → se marcan como vencidos."""
    cr = _crear_abono(client, auth_headers, cliente_test.id, monto=800.0)
    abono_id = cr.json()["id"]

    # Mover la fecha del cobro al pasado
    cobro = db.query(Cobro).filter(Cobro.abono_id == abono_id).first()
    cobro.fecha_cobro = date.today() - timedelta(days=5)
    db.commit()

    r = client.post("/api/abonos/cobros/evaluar-vencidos", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["marcados_vencidos"] >= 1

    cobros_vencidos = client.get("/api/abonos/cobros/vencidos", headers=auth_headers).json()
    assert len(cobros_vencidos) >= 1


def test_evaluar_vencidos_no_afecta_cobros_futuros(client, auth_headers, db, cliente_test):
    """Cobros con fecha_cobro en el futuro no se tocan."""
    cr = _crear_abono(client, auth_headers, cliente_test.id)
    abono_id = cr.json()["id"]

    # La fecha ya es futura (fecha_inicio + 30 días)
    r = client.post("/api/abonos/cobros/evaluar-vencidos", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["marcados_vencidos"] == 0
