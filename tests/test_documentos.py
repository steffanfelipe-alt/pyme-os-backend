from datetime import date

from models.vencimiento import Vencimiento, TipoVencimiento, EstadoVencimiento


def _pdf_falso(contenido: str = "factura de prueba") -> bytes:
    """Genera bytes que simulan un PDF mínimo para tests."""
    return f"%PDF-1.4\n{contenido}".encode()


def test_checklist_sin_vencimientos(client, auth_headers, cliente_test):
    """Cliente sin vencimientos ese período → completo por definición."""
    response = client.get(
        f"/api/clientes/{cliente_test.id}/documentos/checklist?periodo=2025-01",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["vencimientos_activos"] == []
    assert data["completo"] is True
    assert data["completitud_pct"] == 1.0


def test_checklist_con_documentos_faltantes(client, auth_headers, db, cliente_test):
    """Cliente con vencimiento IVA activo y sin documentos → faltantes."""
    venc = Vencimiento(
        cliente_id=cliente_test.id,
        studio_id=cliente_test.studio_id,
        tipo=TipoVencimiento.iva,
        descripcion="IVA Marzo 2026",
        fecha_vencimiento=date(2026, 3, 21),
        estado=EstadoVencimiento.pendiente,
    )
    db.add(venc)
    db.commit()

    response = client.get(
        f"/api/clientes/{cliente_test.id}/documentos/checklist?periodo=2026-03",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["completo"] is False
    assert "factura" in data["faltantes"] or "ddjj" in data["faltantes"]
    assert data["completitud_pct"] == 0.0


def test_checklist_periodo_invalido(client, auth_headers, cliente_test):
    """Período con formato incorrecto → HTTP 400."""
    response = client.get(
        f"/api/clientes/{cliente_test.id}/documentos/checklist?periodo=2026-3",
        headers=auth_headers,
    )
    assert response.status_code == 400


def test_checklist_cliente_inexistente(client, auth_headers):
    """Cliente que no existe → HTTP 404."""
    response = client.get(
        "/api/clientes/99999/documentos/checklist?periodo=2026-03",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_hash_deduplicacion():
    """El mismo contenido binario produce el mismo hash."""
    from services.documento_service import _calcular_hash
    contenido = _pdf_falso("factura única")
    h1 = _calcular_hash(contenido)
    h2 = _calcular_hash(contenido)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 produce 64 caracteres hex


def test_mapeo_vencimiento_documento():
    """El mapeo inverso se construye correctamente."""
    from services.documento_service import MAPEO_VENCIMIENTO_DOCUMENTO
    assert "factura" in MAPEO_VENCIMIENTO_DOCUMENTO["iva"]
    assert "liquidacion_sueldo" in MAPEO_VENCIMIENTO_DOCUMENTO["sueldos_cargas"]
    assert "balance" in MAPEO_VENCIMIENTO_DOCUMENTO["ganancias"]
