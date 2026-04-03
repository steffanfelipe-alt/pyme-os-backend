from datetime import date, timedelta

from models.alerta import AlertaVencimiento, DocumentoRequerido
from models.documento import Documento, EstadoDocumento, TipoDocumento
from models.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento


# Mapeo base mínimo para tests (iva → factura + ddjj)
_SEED_DOCS_REQUERIDOS = [
    {"tipo_vencimiento": "iva", "tipo_documento": "factura"},
    {"tipo_vencimiento": "iva", "tipo_documento": "ddjj"},
]


def _seed_docs_requeridos(db):
    for row in _SEED_DOCS_REQUERIDOS:
        db.add(DocumentoRequerido(**row))
    db.commit()


def _crear_vencimiento(db, cliente_id, dias: int):
    """Vencimiento IVA pendiente con fecha_vencimiento = hoy + dias."""
    venc = Vencimiento(
        cliente_id=cliente_id,
        tipo=TipoVencimiento.iva,
        descripcion="IVA test",
        fecha_vencimiento=date.today() + timedelta(days=dias),
        estado=EstadoVencimiento.pendiente,
    )
    db.add(venc)
    db.commit()
    db.refresh(venc)
    return venc


def _subir_documento(db, cliente_id, tipo: TipoDocumento, periodo: str):
    doc = Documento(
        cliente_id=cliente_id,
        nombre_original=f"{tipo.value}_{periodo}.pdf",
        ruta_archivo=f"uploads/test/{tipo.value}.pdf",
        tipo_documento=tipo,
        estado=EstadoDocumento.procesado,
        metadatos={"periodo": periodo},
        activo=True,
    )
    db.add(doc)
    db.commit()
    return doc


def _periodo(dias: int) -> str:
    """Período YYYY-MM de la fecha hoy + dias."""
    return (date.today() + timedelta(days=dias)).strftime("%Y-%m")


# --- Tests ---

def test_alerta_informativa_documentacion_completa(client, auth_headers, db, cliente_test):
    """Vencimiento en 2 días con documentación completa → alerta informativa."""
    _seed_docs_requeridos(db)
    venc = _crear_vencimiento(db, cliente_test.id, dias=2)
    periodo = _periodo(2)
    _subir_documento(db, cliente_test.id, TipoDocumento.factura, periodo)
    _subir_documento(db, cliente_test.id, TipoDocumento.ddjj, periodo)

    response = client.post("/api/alerts/generate", headers=auth_headers)
    assert response.status_code == 201
    alertas = response.json()
    alerta = next((a for a in alertas if a["vencimiento_id"] == venc.id), None)
    assert alerta is not None
    assert alerta["nivel"] == "informativa"
    assert alerta["documentos_faltantes"] == []


def test_alerta_advertencia_con_faltantes(client, auth_headers, db, cliente_test):
    """Vencimiento en 4 días con documentos faltantes → alerta advertencia."""
    _seed_docs_requeridos(db)
    venc = _crear_vencimiento(db, cliente_test.id, dias=4)
    # Solo un documento de los dos requeridos
    periodo = _periodo(4)
    _subir_documento(db, cliente_test.id, TipoDocumento.factura, periodo)

    response = client.post("/api/alerts/generate", headers=auth_headers)
    assert response.status_code == 201
    alertas = response.json()
    alerta = next((a for a in alertas if a["vencimiento_id"] == venc.id), None)
    assert alerta is not None
    assert alerta["nivel"] == "advertencia"
    assert "ddjj" in alerta["documentos_faltantes"]


def test_alerta_critica_con_faltantes(client, auth_headers, db, cliente_test):
    """Vencimiento en 2 días con documentos faltantes → alerta critica."""
    _seed_docs_requeridos(db)
    venc = _crear_vencimiento(db, cliente_test.id, dias=2)
    # Sin documentos

    response = client.post("/api/alerts/generate", headers=auth_headers)
    assert response.status_code == 201
    alertas = response.json()
    alerta = next((a for a in alertas if a["vencimiento_id"] == venc.id), None)
    assert alerta is not None
    assert alerta["nivel"] == "critica"
    assert set(alerta["documentos_faltantes"]) == {"factura", "ddjj"}


def test_sin_alerta_fuera_del_umbral(client, auth_headers, db, cliente_test):
    """Vencimiento con más de 5 días y documentación completa → no genera alerta."""
    _seed_docs_requeridos(db)
    venc = _crear_vencimiento(db, cliente_test.id, dias=10)
    periodo = _periodo(10)
    _subir_documento(db, cliente_test.id, TipoDocumento.factura, periodo)
    _subir_documento(db, cliente_test.id, TipoDocumento.ddjj, periodo)

    response = client.post("/api/alerts/generate", headers=auth_headers)
    assert response.status_code == 201
    alertas = response.json()
    alerta = next((a for a in alertas if a["vencimiento_id"] == venc.id), None)
    assert alerta is None


def test_generar_dos_veces_no_duplica(client, auth_headers, db, cliente_test):
    """Generar alertas dos veces para el mismo vencimiento → solo una alerta, actualizada."""
    _seed_docs_requeridos(db)
    venc = _crear_vencimiento(db, cliente_test.id, dias=2)

    client.post("/api/alerts/generate", headers=auth_headers)
    client.post("/api/alerts/generate", headers=auth_headers)

    snapshots = db.query(AlertaVencimiento).filter(
        AlertaVencimiento.vencimiento_id == venc.id,
        AlertaVencimiento.resuelta_at == None,
    ).all()
    assert len(snapshots) == 1


def test_resumen_alertas_conteos(client, auth_headers, db, cliente_test):
    """GET /api/alerts/summary retorna los tres conteos correctamente."""
    _seed_docs_requeridos(db)
    # Critica: 2 días sin docs
    _crear_vencimiento(db, cliente_test.id, dias=2)
    # Advertencia: 4 días con un doc faltante
    venc_adv = _crear_vencimiento(db, cliente_test.id, dias=4)
    _subir_documento(db, cliente_test.id, TipoDocumento.factura, _periodo(4))

    client.post("/api/alerts/generate", headers=auth_headers)

    response = client.get("/api/alerts/summary", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "criticas" in data
    assert "advertencias" in data
    assert "informativas" in data
    assert data["criticas"] >= 1
    assert data["advertencias"] >= 1


def test_resolver_alerta(client, auth_headers, db, cliente_test):
    """PATCH /api/alerts/{id}/resolve marca la alerta como resuelta."""
    _seed_docs_requeridos(db)
    _crear_vencimiento(db, cliente_test.id, dias=2)

    gen = client.post("/api/alerts/generate", headers=auth_headers)
    assert gen.status_code == 201
    alertas_generadas = gen.json()
    assert len(alertas_generadas) >= 1

    # Obtener el id de la alerta desde la DB
    alerta = db.query(AlertaVencimiento).first()
    assert alerta is not None

    response = client.patch(f"/api/alerts/{alerta.id}/resolve", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == alerta.id
    assert data["resuelta_at"] is not None

    # No debe aparecer en el listado de activas
    lista = client.get("/api/alerts", headers=auth_headers)
    ids_activas = [a["id"] for a in lista.json()]
    assert alerta.id not in ids_activas
