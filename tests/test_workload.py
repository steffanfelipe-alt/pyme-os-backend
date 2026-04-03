from datetime import date, timedelta

from models.tarea import EstadoTarea, PrioridadTarea, TipoTarea, Tarea


def _crear_tarea(db, cliente_id, empleado_id, horas=3.0, dias_hasta_vencimiento=7):
    tarea = Tarea(
        cliente_id=cliente_id,
        empleado_id=empleado_id,
        titulo="Tarea de prueba",
        tipo=TipoTarea.tarea,
        estado=EstadoTarea.pendiente,
        prioridad=PrioridadTarea.media,
        fecha_limite=date.today() + timedelta(days=dias_hasta_vencimiento),
        horas_estimadas=horas,
        activo=True,
    )
    db.add(tarea)
    db.commit()
    return tarea


def test_panel_carga_sin_tareas(client, auth_headers, empleado_test):
    """Empleado sin tareas → carga 0%, nivel disponible."""
    response = client.get("/api/workload/team", headers=auth_headers)
    assert response.status_code == 200
    empleados = response.json()
    lucas = next((e for e in empleados if e["empleado_id"] == empleado_test.id), None)
    assert lucas is not None
    assert lucas["horas_comprometidas"] == 0.0
    assert lucas["nivel"] == "disponible"


def test_panel_carga_con_tareas(client, auth_headers, db, empleado_test, cliente_test):
    """Empleado con tareas → horas comprometidas reflejan la suma."""
    _crear_tarea(db, cliente_test.id, empleado_test.id, horas=5.0)
    _crear_tarea(db, cliente_test.id, empleado_test.id, horas=3.0)

    response = client.get("/api/workload/team", headers=auth_headers)
    assert response.status_code == 200
    empleados = response.json()
    lucas = next((e for e in empleados if e["empleado_id"] == empleado_test.id), None)
    assert lucas["horas_comprometidas"] == 8.0


def test_resumen_carga(client, auth_headers, empleado_test):
    """El resumen ejecutivo retorna conteos por nivel."""
    response = client.get("/api/workload/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "sobrecargados" in data
    assert "ocupados" in data
    assert "disponibles" in data
    assert "tareas_sin_asignar" in data


def test_detalle_empleado(client, auth_headers, db, empleado_test, cliente_test):
    """El detalle incluye la lista de tareas del empleado."""
    _crear_tarea(db, cliente_test.id, empleado_test.id, horas=2.0)
    response = client.get(
        f"/api/workload/employees/{empleado_test.id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["empleado_id"] == empleado_test.id
    assert len(data["tareas"]) >= 1


def test_detalle_empleado_inexistente(client, auth_headers):
    """Empleado que no existe → HTTP 404."""
    response = client.get("/api/workload/employees/99999", headers=auth_headers)
    assert response.status_code == 404


def test_tarea_sin_horas_usa_default(client, auth_headers, db, empleado_test, cliente_test):
    """Tarea sin horas_estimadas usa el valor default de 2.0 horas."""
    tarea = Tarea(
        cliente_id=cliente_test.id,
        empleado_id=empleado_test.id,
        titulo="Sin horas",
        tipo=TipoTarea.tarea,
        estado=EstadoTarea.pendiente,
        prioridad=PrioridadTarea.media,
        fecha_limite=date.today() + timedelta(days=5),
        horas_estimadas=None,
        activo=True,
    )
    db.add(tarea)
    db.commit()

    response = client.get(
        f"/api/workload/employees/{empleado_test.id}",
        headers=auth_headers,
    )
    tareas = response.json()["tareas"]
    tarea_sin_horas = next(
        (t for t in tareas if t["titulo"] == "Sin horas"), None
    )
    assert tarea_sin_horas is not None
    assert tarea_sin_horas["horas_estimadas"] == 2.0
