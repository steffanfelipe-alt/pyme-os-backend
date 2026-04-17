"""Tests — D2 tipo_cliente + honorario_base, D3 tiempo-por-cliente"""
from decimal import Decimal
from datetime import date, timedelta

import pytest
from models.cliente import Cliente, TipoPersona, CondicionFiscal, TipoCliente
from models.empleado import Empleado, RolEmpleado
from models.studio import Studio
from models.tarea import Tarea, TipoTarea, EstadoTarea, PrioridadTarea
from models.tarea_sesion import TareaSesion
from models.usuario import Usuario
from auth import hash_password, create_access_token


# ── helpers ───────────────────────────────────────────────────────────────────

def _studio(db, nombre="Estudio"):
    s = Studio(nombre=nombre)
    db.add(s)
    db.flush()
    return s


def _token(db, studio_id, email="dueno@t.com"):
    u = Usuario(email=email, password_hash=hash_password("pass"), nombre="D", studio_id=studio_id)
    db.add(u)
    db.flush()
    e = Empleado(nombre="D", email=email, rol=RolEmpleado.dueno, activo=True, studio_id=studio_id)
    db.add(e)
    db.commit()
    return create_access_token({"sub": str(u.id), "email": email, "rol": "dueno",
                                 "empleado_id": e.id, "studio_id": studio_id})


def _cliente(db, studio_id, cuit, tipo=TipoCliente.otro, nombre="Cliente Test"):
    c = Cliente(
        studio_id=studio_id,
        tipo_persona=TipoPersona.fisica,
        nombre=nombre,
        cuit_cuil=cuit,
        condicion_fiscal=CondicionFiscal.monotributista,
        tipo_cliente=tipo,
        honorarios_mensuales=Decimal("1000"),
        activo=True,
    )
    db.add(c)
    db.flush()
    return c


# ── D2: tipo_cliente ──────────────────────────────────────────────────────────

def test_cliente_create_con_tipo_monotributista(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    db.commit()

    r = client.post("/api/clientes", json={
        "tipo_persona": "fisica",
        "nombre": "Juan Mono",
        "cuit_cuil": "20-12345678-6",
        "condicion_fiscal": "monotributista",
        "tipo_cliente": "monotributista",
        "honorario_base": "500",
    }, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 201
    data = r.json()
    assert data["tipo_cliente"] == "monotributista"
    assert float(data["honorario_base"]) == 500.0


def test_cliente_create_tipo_default_es_otro(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    db.commit()

    r = client.post("/api/clientes", json={
        "tipo_persona": "fisica",
        "nombre": "Ana Default",
        "cuit_cuil": "23-12345678-5",
        "condicion_fiscal": "monotributista",
    }, headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 201
    assert r.json()["tipo_cliente"] == "otro"


def test_cliente_update_tipo(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    c = _cliente(db, s.id, "20-12345678-6", TipoCliente.otro)
    db.commit()

    r = client.put(f"/api/clientes/{c.id}",
                   json={"tipo_cliente": "sociedad"},
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json()["tipo_cliente"] == "sociedad"


def test_get_clientes_por_tipo_filtra_correctamente(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    _cliente(db, s.id, "20-12345678-6", TipoCliente.monotributista, "Mono Uno")
    _cliente(db, s.id, "23-12345678-5", TipoCliente.sociedad, "Sociedad SA")
    db.commit()

    r = client.get("/api/clientes/por-tipo/monotributista",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["tipo_cliente"] == "monotributista"


def test_get_clientes_por_tipo_vacio_devuelve_lista_no_404(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    db.commit()

    r = client.get("/api/clientes/por-tipo/empleador",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json() == []


def test_get_clientes_por_tipo_otro_studio_no_aparece(client, db):
    s1 = _studio(db, "Studio1")
    s2 = _studio(db, "Studio2")
    tok1 = _token(db, s1.id, "d1@t.com")
    _cliente(db, s2.id, "20-12345678-6", TipoCliente.monotributista)
    db.commit()

    r = client.get("/api/clientes/por-tipo/monotributista",
                   headers={"Authorization": f"Bearer {tok1}"})
    assert r.status_code == 200
    assert r.json() == []


def test_reporte_rentabilidad_por_tipo_studio_isolation(client, db):
    s1 = _studio(db, "S1")
    s2 = _studio(db, "S2")
    tok1 = _token(db, s1.id, "d1@rpt.com")
    _cliente(db, s2.id, "20-12345678-6", TipoCliente.monotributista)
    db.commit()

    r = client.get("/api/reportes/rentabilidad-por-tipo",
                   headers={"Authorization": f"Bearer {tok1}"})
    assert r.status_code == 200
    # s1 no tiene clientes → lista vacía
    assert r.json() == []


# ── D3: tiempo-por-cliente ────────────────────────────────────────────────────

def test_reporte_tiempo_por_cliente_calcula_minutos(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    c = _cliente(db, s.id, "20-12345678-6")
    t = Tarea(studio_id=s.id, titulo="T", tipo=TipoTarea.otro, prioridad=PrioridadTarea.normal,
              estado=EstadoTarea.completada, cliente_id=c.id, activo=True,
              fecha_completada=date.today())
    db.add(t)
    db.flush()
    from datetime import datetime, timezone
    sesion = TareaSesion(tarea_id=t.id, inicio=datetime.now(timezone.utc), minutos=90)
    db.add(sesion)
    db.commit()

    hoy = date.today()
    r = client.get(f"/api/reportes/tiempo-por-cliente?fecha_desde={hoy}&fecha_hasta={hoy}",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["minutos_totales"] == 90
    assert data[0]["horas_totales"] == 1.5


def test_reporte_tiempo_por_cliente_calcula_costo_hora(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    c = _cliente(db, s.id, "20-12345678-6")
    t = Tarea(studio_id=s.id, titulo="T", tipo=TipoTarea.otro, prioridad=PrioridadTarea.normal,
              estado=EstadoTarea.completada, cliente_id=c.id, activo=True,
              fecha_completada=date.today())
    db.add(t)
    db.flush()
    from datetime import datetime, timezone
    sesion = TareaSesion(tarea_id=t.id, inicio=datetime.now(timezone.utc), minutos=60)
    db.add(sesion)
    db.commit()

    hoy = date.today()
    r = client.get(f"/api/reportes/tiempo-por-cliente?fecha_desde={hoy}&fecha_hasta={hoy}",
                   headers={"Authorization": f"Bearer {tok}"})
    data = r.json()
    assert data[0]["costo_hora_estimado"] is not None  # honorario/1h


def test_reporte_tiempo_por_cliente_sin_sesiones(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    db.commit()

    hoy = date.today()
    r = client.get(f"/api/reportes/tiempo-por-cliente?fecha_desde={hoy}&fecha_hasta={hoy}",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json() == []


def test_reporte_tiempo_por_cliente_studio_isolation(client, db):
    s1 = _studio(db, "S1")
    s2 = _studio(db, "S2")
    tok1 = _token(db, s1.id, "d1@tmp.com")
    c = _cliente(db, s2.id, "20-12345678-6")
    t = Tarea(studio_id=s2.id, titulo="T", tipo=TipoTarea.otro, prioridad=PrioridadTarea.normal,
              estado=EstadoTarea.pendiente, cliente_id=c.id, activo=True)
    db.add(t)
    db.flush()
    from datetime import datetime, timezone
    sesion = TareaSesion(tarea_id=t.id, inicio=datetime.now(timezone.utc), minutos=60)
    db.add(sesion)
    db.commit()

    hoy = date.today()
    r = client.get(f"/api/reportes/tiempo-por-cliente?fecha_desde={hoy}&fecha_hasta={hoy}",
                   headers={"Authorization": f"Bearer {tok1}"})
    assert r.status_code == 200
    assert r.json() == []


def test_reporte_tiempo_por_cliente_rango_fechas(client, db):
    s = _studio(db)
    tok = _token(db, s.id)
    c = _cliente(db, s.id, "20-12345678-6")
    t = Tarea(studio_id=s.id, titulo="T", tipo=TipoTarea.otro, prioridad=PrioridadTarea.normal,
              estado=EstadoTarea.pendiente, cliente_id=c.id, activo=True)
    db.add(t)
    db.flush()
    from datetime import datetime, timezone
    # Sesión de hace 30 días — fuera del rango
    inicio_viejo = datetime(2020, 1, 1, tzinfo=timezone.utc)
    sesion = TareaSesion(tarea_id=t.id, inicio=inicio_viejo, minutos=120)
    db.add(sesion)
    db.commit()

    hoy = date.today()
    r = client.get(f"/api/reportes/tiempo-por-cliente?fecha_desde={hoy}&fecha_hasta={hoy}",
                   headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json() == []
