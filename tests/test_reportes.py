"""
Tests del módulo de reportes.
"""
from datetime import date, timedelta

import pytest

from models.cliente import Cliente, TipoPersona, CondicionFiscal
from models.empleado import Empleado, RolEmpleado
from models.tarea import Tarea, TipoTarea, PrioridadTarea, EstadoTarea
from models.vencimiento import Vencimiento, TipoVencimiento, EstadoVencimiento
from tests.conftest import _crear_token_con_rol


PERIODO_ACTUAL = date.today().strftime("%Y-%m")


@pytest.fixture()
def token_dueno_rep(db):
    return _crear_token_con_rol(db, "dueno_rep@pymeos.com", "Dueño Rep", "dueno")


@pytest.fixture()
def headers_dueno(token_dueno_rep):
    return {"Authorization": f"Bearer {token_dueno_rep}"}


# ─── Studio Config ────────────────────────────────────────────────────────────

def test_obtener_config_crea_singleton(client, headers_dueno):
    resp = client.get("/api/reportes/config", headers=headers_dueno)
    assert resp.status_code == 200
    data = resp.json()
    assert data["moneda"] == "ARS"
    assert data["zona_horaria"] == "America/Argentina/Buenos_Aires"


def test_actualizar_config(client, headers_dueno):
    resp = client.put(
        "/api/reportes/config",
        json={"tarifa_hora_pesos": 5000.0},
        headers=headers_dueno,
    )
    assert resp.status_code == 200
    assert resp.json()["tarifa_hora_pesos"] == 5000.0


def test_config_no_autorizado_para_contador(client, db):
    token = _crear_token_con_rol(db, "cont_rep@pymeos.com", "Cont Rep", "contador")
    resp = client.get("/api/reportes/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


# ─── Reporte 1: Carga ────────────────────────────────────────────────────────

def test_reporte_carga_vacio(client, headers_dueno):
    resp = client.get(f"/api/reportes/carga?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    data = resp.json()
    assert data["periodo"] == PERIODO_ACTUAL
    assert "empleados" in data


def test_reporte_carga_con_datos(client, db, headers_dueno, cliente_test):
    emp = Empleado(nombre="María Reportes", email="maria_rep@estudio.com", rol=RolEmpleado.contador, activo=True)
    db.add(emp)
    db.flush()

    # Crear 12 tareas pendientes → nivel alta
    for i in range(12):
        t = Tarea(
            cliente_id=cliente_test.id,
            empleado_id=emp.id,
            titulo=f"Tarea {i}",
            tipo=TipoTarea.tarea,
            prioridad=PrioridadTarea.media,
            estado=EstadoTarea.pendiente,
            activo=True,
        )
        db.add(t)
    db.commit()

    resp = client.get(f"/api/reportes/carga?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    empleados = resp.json()["empleados"]
    maria = next((e for e in empleados if e["nombre"] == "María Reportes"), None)
    assert maria is not None
    assert maria["nivel_carga"] == "alta"
    assert maria["tareas_pendientes"] == 12


def test_reporte_carga_nivel_baja(client, db, headers_dueno, cliente_test):
    emp = Empleado(nombre="Lucas Carga", email="lucas_carga@estudio.com", rol=RolEmpleado.contador, activo=True)
    db.add(emp)
    db.flush()
    t = Tarea(
        cliente_id=cliente_test.id, empleado_id=emp.id, titulo="Única",
        tipo=TipoTarea.tarea, prioridad=PrioridadTarea.media, estado=EstadoTarea.pendiente, activo=True,
    )
    db.add(t)
    db.commit()
    resp = client.get(f"/api/reportes/carga?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    lucas = next((e for e in resp.json()["empleados"] if e["nombre"] == "Lucas Carga"), None)
    assert lucas["nivel_carga"] == "baja"


def test_reporte_carga_sin_periodo_usa_mes_actual(client, headers_dueno):
    resp = client.get("/api/reportes/carga", headers=headers_dueno)
    assert resp.status_code == 200
    assert resp.json()["periodo"] == PERIODO_ACTUAL


# ─── Reporte 2: Rentabilidad ─────────────────────────────────────────────────

def test_rentabilidad_sin_tarifa_retorna_400(client, headers_dueno):
    """Si no hay tarifa configurada, debe retornar 400 con mensaje descriptivo."""
    resp = client.get(f"/api/reportes/rentabilidad?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 400
    assert "tarifa-hora" in resp.json()["detail"].lower()


def test_rentabilidad_con_tarifa(client, db, headers_dueno):
    # Configurar tarifa
    client.put("/api/reportes/config", json={"tarifa_hora_pesos": 4000.0}, headers=headers_dueno)

    resp = client.get(f"/api/reportes/rentabilidad?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tarifa_hora"] == 4000.0
    assert "clientes" in data


def test_rentabilidad_cliente_sin_honorario(client, db, headers_dueno):
    """Cliente sin honorario aparece con sin_honorario=True, sin crashear."""
    client.put("/api/reportes/config", json={"tarifa_hora_pesos": 4000.0}, headers=headers_dueno)
    # Asegurar que hay un cliente sin honorario
    cliente_sin = Cliente(
        tipo_persona=TipoPersona.juridica, nombre="Sin Honorario SRL",
        cuit_cuil="20-99999999-0", condicion_fiscal=CondicionFiscal.responsable_inscripto,
        honorarios_mensuales=None, activo=True,
    )
    db.add(cliente_sin)
    db.commit()

    resp = client.get(f"/api/reportes/rentabilidad?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    clientes = resp.json()["clientes"]
    sin_hon = next((c for c in clientes if c["nombre"] == "Sin Honorario SRL"), None)
    assert sin_hon is not None
    assert sin_hon["sin_honorario"] is True
    assert sin_hon["margen_pct"] is None


# ─── Reporte 3: Vencimientos ─────────────────────────────────────────────────

def test_reporte_vencimientos_vacio(client, headers_dueno):
    resp = client.get(f"/api/reportes/vencimientos?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    data = resp.json()
    assert "resumen" in data
    assert "vencimientos" in data


def test_reporte_vencimientos_con_alerta(client, db, headers_dueno, cliente_test):
    hoy = date.today()
    # Vencimiento en 3 días → alerta
    v_alerta = Vencimiento(
        cliente_id=cliente_test.id, tipo=TipoVencimiento.iva,
        descripcion="IVA Alerta", fecha_vencimiento=hoy + timedelta(days=3),
        estado=EstadoVencimiento.pendiente,
    )
    # Vencimiento en 20 días → sin alerta
    v_normal = Vencimiento(
        cliente_id=cliente_test.id, tipo=TipoVencimiento.iva,
        descripcion="IVA Normal", fecha_vencimiento=hoy + timedelta(days=20),
        estado=EstadoVencimiento.pendiente,
    )
    # Vencimiento cumplido en 3 días → no alerta (ya presentado)
    v_cumplido = Vencimiento(
        cliente_id=cliente_test.id, tipo=TipoVencimiento.iva,
        descripcion="IVA Cumplido", fecha_vencimiento=hoy + timedelta(days=2),
        estado=EstadoVencimiento.cumplido,
    )
    db.add_all([v_alerta, v_normal, v_cumplido])
    db.commit()

    resp = client.get(f"/api/reportes/vencimientos?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    venc = resp.json()["vencimientos"]

    alerta_item = next((v for v in venc if v["descripcion"] == "IVA Alerta"), None)
    normal_item = next((v for v in venc if v["descripcion"] == "IVA Normal"), None)
    cumplido_item = next((v for v in venc if v["descripcion"] == "IVA Cumplido"), None)

    assert alerta_item["alerta"] is True
    assert normal_item["alerta"] is False
    assert cumplido_item["alerta"] is False  # cumplido no genera alerta


def test_reporte_vencimientos_resumen(client, db, headers_dueno, cliente_test):
    hoy = date.today()
    db.add_all([
        Vencimiento(cliente_id=cliente_test.id, tipo=TipoVencimiento.iva, descripcion="P1",
                    fecha_vencimiento=hoy + timedelta(days=5), estado=EstadoVencimiento.pendiente),
        Vencimiento(cliente_id=cliente_test.id, tipo=TipoVencimiento.iva, descripcion="C1",
                    fecha_vencimiento=hoy + timedelta(days=10), estado=EstadoVencimiento.cumplido),
        Vencimiento(cliente_id=cliente_test.id, tipo=TipoVencimiento.iva, descripcion="V1",
                    fecha_vencimiento=hoy - timedelta(days=5), estado=EstadoVencimiento.vencido),
    ])
    db.commit()

    resp = client.get(f"/api/reportes/vencimientos?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    resumen = resp.json()["resumen"]
    assert resumen["pendientes"] >= 1
    assert resumen["presentados"] >= 1
    # vencido está fuera del mes actual si el mes actual ya pasó, pero para el test usamos el mes actual


def test_reporte_vencimientos_filtro_estado(client, db, headers_dueno, cliente_test):
    hoy = date.today()
    db.add(Vencimiento(
        cliente_id=cliente_test.id, tipo=TipoVencimiento.iva, descripcion="Filtrado",
        fecha_vencimiento=hoy + timedelta(days=5), estado=EstadoVencimiento.pendiente,
    ))
    db.commit()

    resp = client.get(
        f"/api/reportes/vencimientos?periodo={PERIODO_ACTUAL}&estado=pendiente",
        headers=headers_dueno,
    )
    assert resp.status_code == 200
    for v in resp.json()["vencimientos"]:
        assert v["estado"] == "pendiente"


# ─── Reporte 4: Eficiencia procesos ──────────────────────────────────────────

def test_reporte_procesos_sin_instancias(client, headers_dueno):
    """Sin instancias completadas, el reporte de procesos retorna lista vacía."""
    resp = client.get(f"/api/reportes/procesos?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    assert resp.json()["procesos"] == []


# ─── Resumen ejecutivo ────────────────────────────────────────────────────────

def test_reporte_resumen_estructura(client, headers_dueno):
    resp = client.get(f"/api/reportes/resumen?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    data = resp.json()
    assert "carga" in data
    assert "rentabilidad" in data
    assert "vencimientos" in data
    assert "procesos" in data
    assert data["periodo"] == PERIODO_ACTUAL


def test_reporte_resumen_sin_periodo(client, headers_dueno):
    resp = client.get("/api/reportes/resumen", headers=headers_dueno)
    assert resp.status_code == 200
    assert resp.json()["periodo"] == PERIODO_ACTUAL


def test_periodo_invalido(client, headers_dueno):
    resp = client.get("/api/reportes/carga?periodo=2025-13", headers=headers_dueno)
    assert resp.status_code == 400


# ─── Studio identity ─────────────────────────────────────────────────────────

def test_actualizar_nombre_estudio(client, headers_dueno):
    resp = client.put(
        "/api/reportes/config",
        json={"nombre_estudio": "Estudio Contable López", "email_estudio": "info@lopez.com"},
        headers=headers_dueno,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["nombre_estudio"] == "Estudio Contable López"
    assert data["email_estudio"] == "info@lopez.com"


def test_config_incluye_nombre_y_email(client, headers_dueno):
    client.put("/api/reportes/config", json={"nombre_estudio": "López & Asoc."}, headers=headers_dueno)
    resp = client.get("/api/reportes/config", headers=headers_dueno)
    assert resp.status_code == 200
    assert resp.json()["nombre_estudio"] == "López & Asoc."


# ─── Export CSV ──────────────────────────────────────────────────────────────

def test_export_vencimientos_csv(client, db, headers_dueno, cliente_test):
    venc = Vencimiento(
        cliente_id=cliente_test.id,
        tipo=TipoVencimiento.iva,
        descripcion="IVA test",
        fecha_vencimiento=date.today(),
        estado=EstadoVencimiento.pendiente,
    )
    db.add(venc)
    db.commit()

    resp = client.get(f"/api/reportes/vencimientos/export.csv?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    content = resp.text
    assert "cliente" in content
    assert "IVA test" in content or "iva" in content


def test_export_carga_csv(client, headers_dueno):
    resp = client.get(f"/api/reportes/carga/export.csv?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "empleado" in resp.text


def test_export_rentabilidad_csv_sin_tarifa(client, headers_dueno):
    """Sin tarifa configurada → 400 (igual que el endpoint JSON)."""
    resp = client.get(f"/api/reportes/rentabilidad/export.csv?periodo={PERIODO_ACTUAL}", headers=headers_dueno)
    assert resp.status_code == 400
