from datetime import date

from models.alerta import AlertaVencimiento
from models.cliente import Cliente, CondicionFiscal, TipoPersona
from models.informe_ejecutivo import InformeEjecutivo
from models.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento

PERIODO = "2026-03"


def _crear_cliente(db, nombre="Empresa Test", cuit="20-12345678-6"):
    cliente = Cliente(
        tipo_persona=TipoPersona.juridica,
        nombre=nombre,
        cuit_cuil=cuit,
        condicion_fiscal=CondicionFiscal.responsable_inscripto,
        activo=True,
    )
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


def _crear_vencimiento(db, cliente_id, fecha=date(2026, 3, 20)):
    venc = Vencimiento(
        cliente_id=cliente_id,
        tipo=TipoVencimiento.iva,
        descripcion="IVA Marzo",
        fecha_vencimiento=fecha,
        estado=EstadoVencimiento.pendiente,
    )
    db.add(venc)
    db.commit()
    db.refresh(venc)
    return venc


def _crear_alerta_critica(db, vencimiento_id, cliente_id):
    alerta = AlertaVencimiento(
        vencimiento_id=vencimiento_id,
        cliente_id=cliente_id,
        nivel="critica",
        dias_restantes=1,
        documentos_faltantes=["factura"],
        mensaje="CRÍTICO: vence mañana",
        vista=False,
    )
    db.add(alerta)
    db.commit()
    db.refresh(alerta)
    return alerta


# --- Tests ---

def test_generar_informe_estructura_base(client, auth_headers):
    """Período sin datos → 201, estructura con todas las keys presentes."""
    response = client.post(
        "/api/reports/generate",
        json={"periodo": PERIODO},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    for key in ("id", "periodo", "total_clientes_activos", "alertas_criticas",
                "clientes_riesgo_rojo", "resumen_vencimientos",
                "resumen_rentabilidad", "resumen_alertas", "resumen_riesgo",
                "ai_interpretation", "created_at"):
        assert key in data, f"Falta la key: {key}"
    assert data["periodo"] == PERIODO
    assert data["total_clientes_activos"] == 0
    assert data["resumen_vencimientos"]["total"] == 0


def test_generar_informe_con_clientes_y_alertas(client, auth_headers, db):
    """Con cliente + alerta crítica → alertas_criticas >= 1, total_clientes_activos = 1."""
    cliente = _crear_cliente(db)
    venc = _crear_vencimiento(db, cliente.id)
    _crear_alerta_critica(db, venc.id, cliente.id)

    response = client.post(
        "/api/reports/generate",
        json={"periodo": PERIODO},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["total_clientes_activos"] == 1
    assert data["alertas_criticas"] >= 1
    assert data["resumen_vencimientos"]["total"] >= 1
    assert data["resumen_alertas"]["criticas"] >= 1


def test_generar_informe_periodo_invalido(client, auth_headers):
    """Formato de período inválido → 400."""
    for periodo_invalido in ("2026-13", "26-03", "2026/03", "hola"):
        response = client.post(
            "/api/reports/generate",
            json={"periodo": periodo_invalido},
            headers=auth_headers,
        )
        assert response.status_code == 400, f"Esperaba 400 para '{periodo_invalido}'"


def test_obtener_informe_existente(client, auth_headers):
    """POST genera informe, luego GET por id → 200 con datos correctos."""
    gen = client.post(
        "/api/reports/generate",
        json={"periodo": PERIODO},
        headers=auth_headers,
    )
    assert gen.status_code == 201
    informe_id = gen.json()["id"]

    response = client.get(f"/api/reports/{informe_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == informe_id
    assert data["periodo"] == PERIODO


def test_obtener_informe_no_encontrado(client, auth_headers):
    """GET /reports/9999 → 404."""
    response = client.get("/api/reports/9999", headers=auth_headers)
    assert response.status_code == 404


def test_listar_informes_vacio_y_con_datos(client, auth_headers):
    """Lista vacía sin datos, luego genera uno y aparece en la lista."""
    lista_vacia = client.get("/api/reports/", headers=auth_headers)
    assert lista_vacia.status_code == 200
    assert lista_vacia.json() == []

    client.post(
        "/api/reports/generate",
        json={"periodo": PERIODO},
        headers=auth_headers,
    )

    lista = client.get("/api/reports/", headers=auth_headers)
    assert lista.status_code == 200
    assert len(lista.json()) == 1
    assert lista.json()[0]["periodo"] == PERIODO


def test_generar_informe_sobreescribe_mismo_periodo(client, auth_headers, db):
    """Generar el mismo período dos veces → solo persiste un informe."""
    client.post("/api/reports/generate", json={"periodo": PERIODO}, headers=auth_headers)

    _crear_cliente(db)
    client.post("/api/reports/generate", json={"periodo": PERIODO}, headers=auth_headers)

    lista = client.get("/api/reports/", headers=auth_headers)
    assert lista.status_code == 200
    assert len(lista.json()) == 1
    assert lista.json()[0]["total_clientes_activos"] == 1


def test_listar_informes_filtro_periodo(client, auth_headers):
    """Filtrar por período retorna solo los informes del período indicado."""
    client.post("/api/reports/generate", json={"periodo": "2026-02"}, headers=auth_headers)
    client.post("/api/reports/generate", json={"periodo": "2026-03"}, headers=auth_headers)

    lista = client.get("/api/reports/?periodo=2026-02", headers=auth_headers)
    assert lista.status_code == 200
    resultados = lista.json()
    assert len(resultados) == 1
    assert resultados[0]["periodo"] == "2026-02"
