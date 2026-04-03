from datetime import date

from models.cliente import Cliente, TipoPersona, CondicionFiscal
from models.tarea import EstadoTarea, PrioridadTarea, TipoTarea, Tarea
from models.rentabilidad import RentabilidadMensual

PERIODO = "2026-03"


def _crear_cliente_con_honorario(db, nombre, cuit, honorario):
    cliente = Cliente(
        tipo_persona=TipoPersona.juridica,
        nombre=nombre,
        cuit_cuil=cuit,
        condicion_fiscal=CondicionFiscal.responsable_inscripto,
        honorarios_mensuales=honorario,
        activo=True,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def _crear_tarea_completada(db, cliente_id, horas_reales=None, horas_estimadas=None,
                             fecha_completada=None, fecha_limite=None):
    tarea = Tarea(
        cliente_id=cliente_id,
        titulo="Tarea completada",
        tipo=TipoTarea.tarea,
        estado=EstadoTarea.completada,
        prioridad=PrioridadTarea.media,
        fecha_completada=fecha_completada or date(2026, 3, 15),
        fecha_limite=fecha_limite,
        horas_estimadas=horas_estimadas,
        horas_reales=horas_reales,
        activo=True,
    )
    db.add(tarea)
    db.commit()
    return tarea


# --- Tests ---

def test_rentabilidad_calculada_correctamente(client, auth_headers, db):
    """Cliente con honorario y tareas con horas_reales → rentabilidad_hora = honorario / horas_reales."""
    cliente = _crear_cliente_con_honorario(db, "Empresa A", "20-12345678-6", 6000.0)
    _crear_tarea_completada(db, cliente.id, horas_reales=4.0, horas_estimadas=3.0)
    _crear_tarea_completada(db, cliente.id, horas_reales=2.0, horas_estimadas=2.0)

    response = client.post(f"/api/profitability/calculate/{PERIODO}", headers=auth_headers)
    assert response.status_code == 201
    resultados = response.json()
    empresa_a = next((r for r in resultados if r["cliente_id"] == cliente.id), None)
    assert empresa_a is not None
    assert empresa_a["horas_reales"] == 6.0
    assert empresa_a["rentabilidad_hora"] == round(6000.0 / 6.0, 2)
    assert empresa_a["honorario_configurado"] is True


def test_rentabilidad_sin_tareas_ese_mes(client, auth_headers, db):
    """Cliente con honorario pero sin tareas completadas → rentabilidad_hora null, sin error."""
    cliente = _crear_cliente_con_honorario(db, "Empresa B", "27-30678265-9", 5000.0)
    # Tarea completada en otro período
    _crear_tarea_completada(db, cliente.id, horas_reales=3.0,
                             fecha_completada=date(2026, 2, 10))

    response = client.post(f"/api/profitability/calculate/{PERIODO}", headers=auth_headers)
    assert response.status_code == 201
    resultados = response.json()
    empresa_b = next((r for r in resultados if r["cliente_id"] == cliente.id), None)
    assert empresa_b is not None
    assert empresa_b["tareas_completadas"] == 0
    assert empresa_b["rentabilidad_hora"] is None


def test_cliente_sin_honorario_aparece_en_lista(client, auth_headers, db):
    """Cliente sin honorario configurado aparece con honorario_configurado: false al final."""
    cliente = Cliente(
        tipo_persona=TipoPersona.fisica,
        nombre="Sin Honorario",
        cuit_cuil="20-30678265-8",
        condicion_fiscal=CondicionFiscal.monotributista,
        honorarios_mensuales=None,
        activo=True,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    _crear_tarea_completada(db, cliente.id, horas_reales=2.0)

    response = client.post(f"/api/profitability/calculate/{PERIODO}", headers=auth_headers)
    assert response.status_code == 201
    resultados = response.json()
    sin_hon = next((r for r in resultados if r["cliente_id"] == cliente.id), None)
    assert sin_hon is not None
    assert sin_hon["honorario_configurado"] is False
    assert sin_hon["rentabilidad_hora"] is None
    # Debe aparecer al final (todos los con rentabilidad van antes)
    assert resultados[-1]["cliente_id"] == cliente.id


def test_division_por_cero_no_explota(client, auth_headers, db):
    """Cliente con honorario y tareas pero horas_reales=0 → rentabilidad_hora null."""
    cliente = _crear_cliente_con_honorario(db, "Empresa C", "30-12345609-2", 3000.0)
    # Tarea sin horas_reales ni horas_estimadas
    tarea = Tarea(
        cliente_id=cliente.id,
        titulo="Sin horas",
        tipo=TipoTarea.tarea,
        estado=EstadoTarea.completada,
        prioridad=PrioridadTarea.media,
        fecha_completada=date(2026, 3, 10),
        horas_estimadas=None,
        horas_reales=None,
        activo=True,
    )
    db.add(tarea)
    db.commit()

    response = client.post(f"/api/profitability/calculate/{PERIODO}", headers=auth_headers)
    assert response.status_code == 201
    resultados = response.json()
    empresa_c = next((r for r in resultados if r["cliente_id"] == cliente.id), None)
    assert empresa_c is not None
    assert empresa_c["horas_reales"] == 0.0
    assert empresa_c["rentabilidad_hora"] is None


def test_historial_cliente_orden_descendente(client, auth_headers, db):
    """El historial retorna períodos en orden descendente."""
    cliente = _crear_cliente_con_honorario(db, "Empresa D", "20-33333333-4", 4000.0)

    for periodo in ["2026-01", "2026-02", "2026-03"]:
        snap = RentabilidadMensual(
            cliente_id=cliente.id,
            periodo=periodo,
            honorario=4000.0,
            horas_reales=5.0,
            rentabilidad_hora=800.0,
            tareas_completadas=2,
            tareas_demoradas=0,
        )
        db.add(snap)
    db.commit()

    response = client.get(
        f"/api/profitability/clients/{cliente.id}/history",
        headers=auth_headers,
    )
    assert response.status_code == 200
    historial = response.json()
    assert len(historial) == 3
    periodos = [h["periodo"] for h in historial]
    assert periodos == sorted(periodos, reverse=True)


def test_recalcular_periodo_sobreescribe_snapshot(client, auth_headers, db):
    """Calcular el mismo período dos veces sobreescribe el snapshot existente."""
    cliente = _crear_cliente_con_honorario(db, "Empresa E", "27-11111111-7", 9000.0)
    _crear_tarea_completada(db, cliente.id, horas_reales=3.0)

    # Primer cálculo
    r1 = client.post(f"/api/profitability/calculate/{PERIODO}", headers=auth_headers)
    assert r1.status_code == 201
    v1 = next(r for r in r1.json() if r["cliente_id"] == cliente.id)
    assert v1["rentabilidad_hora"] == round(9000.0 / 3.0, 2)

    # Agregar más horas y recalcular
    _crear_tarea_completada(db, cliente.id, horas_reales=6.0)
    r2 = client.post(f"/api/profitability/calculate/{PERIODO}", headers=auth_headers)
    assert r2.status_code == 201
    v2 = next(r for r in r2.json() if r["cliente_id"] == cliente.id)
    assert v2["horas_reales"] == 9.0
    assert v2["rentabilidad_hora"] == round(9000.0 / 9.0, 2)

    # Solo debe existir un snapshot para este cliente+período
    snapshots = db.query(RentabilidadMensual).filter(
        RentabilidadMensual.cliente_id == cliente.id,
        RentabilidadMensual.periodo == PERIODO,
    ).all()
    assert len(snapshots) == 1
