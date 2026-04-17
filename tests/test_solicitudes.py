"""Tests E2 — Solicitud automática de documentos faltantes."""
from datetime import date, timedelta

import pytest
from models.alerta import AlertaVencimiento, DocumentoRequerido
from models.solicitud_documento import EstadoSolicitud, SolicitudDocumentoAuto
from models.vencimiento import EstadoVencimiento, TipoVencimiento, Vencimiento


def _seed_docs_requeridos(db):
    db.add(DocumentoRequerido(tipo_vencimiento="iva", tipo_documento="factura"))
    db.add(DocumentoRequerido(tipo_vencimiento="iva", tipo_documento="ddjj"))
    db.commit()


def _crear_alerta_con_faltantes(db, cliente_id, studio_id, faltantes: list[str]):
    venc = Vencimiento(
        studio_id=studio_id,
        cliente_id=cliente_id,
        tipo=TipoVencimiento.iva,
        descripcion="IVA test",
        fecha_vencimiento=date.today() + timedelta(days=3),
        estado=EstadoVencimiento.pendiente,
    )
    db.add(venc)
    db.commit()
    db.refresh(venc)

    alerta = AlertaVencimiento(
        studio_id=studio_id,
        cliente_id=cliente_id,
        vencimiento_id=venc.id,
        nivel="advertencia",
        dias_restantes=3,
        documentos_faltantes=faltantes,
        mensaje="Test alerta",
    )
    db.add(alerta)
    db.commit()
    return alerta, venc


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_generar_solicitudes_crea_por_faltantes(client, auth_headers, db, cliente_test):
    _seed_docs_requeridos(db)
    _crear_alerta_con_faltantes(db, cliente_test.id, cliente_test.studio_id, ["factura", "ddjj"])

    r = client.post("/api/solicitudes-documentos/generar", headers=auth_headers)
    assert r.status_code == 201
    data = r.json()
    assert data["creadas"] == 2
    assert len(data["solicitudes"]) == 2


def test_generar_solicitudes_no_duplica(client, auth_headers, db, cliente_test):
    _seed_docs_requeridos(db)
    _crear_alerta_con_faltantes(db, cliente_test.id, cliente_test.studio_id, ["factura"])

    client.post("/api/solicitudes-documentos/generar", headers=auth_headers)
    r = client.post("/api/solicitudes-documentos/generar", headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["creadas"] == 0  # ya existe, no duplica


def test_listar_solicitudes(client, auth_headers, db, cliente_test):
    _seed_docs_requeridos(db)
    _crear_alerta_con_faltantes(db, cliente_test.id, cliente_test.studio_id, ["factura"])

    client.post("/api/solicitudes-documentos/generar", headers=auth_headers)

    r = client.get("/api/solicitudes-documentos", headers=auth_headers)
    assert r.status_code == 200
    solicitudes = r.json()
    assert len(solicitudes) >= 1
    assert solicitudes[0]["tipo_documento"] == "factura"
    assert solicitudes[0]["estado"] == "pendiente"


def test_marcar_enviada(client, auth_headers, db, cliente_test):
    _seed_docs_requeridos(db)
    _crear_alerta_con_faltantes(db, cliente_test.id, cliente_test.studio_id, ["ddjj"])
    client.post("/api/solicitudes-documentos/generar", headers=auth_headers)

    lista = client.get("/api/solicitudes-documentos", headers=auth_headers).json()
    solicitud_id = lista[0]["id"]

    r = client.patch(f"/api/solicitudes-documentos/{solicitud_id}/enviada?canal=email", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["estado"] == "enviada"
    assert r.json()["canal"] == "email"


def test_marcar_recibida(client, auth_headers, db, cliente_test):
    _seed_docs_requeridos(db)
    _crear_alerta_con_faltantes(db, cliente_test.id, cliente_test.studio_id, ["ddjj"])
    client.post("/api/solicitudes-documentos/generar", headers=auth_headers)

    lista = client.get("/api/solicitudes-documentos", headers=auth_headers).json()
    solicitud_id = lista[0]["id"]

    r = client.patch(f"/api/solicitudes-documentos/{solicitud_id}/recibida", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["estado"] == "recibida"


def test_sin_alertas_no_crea_solicitudes(client, auth_headers, db, cliente_test):
    r = client.post("/api/solicitudes-documentos/generar", headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["creadas"] == 0
