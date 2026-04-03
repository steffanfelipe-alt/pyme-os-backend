def test_crear_vencimiento(client, auth_headers, cliente_test):
    response = client.post("/api/vencimientos", json={
        "cliente_id": cliente_test.id,
        "tipo": "iva",
        "descripcion": "IVA Abril 2026",
        "fecha_vencimiento": "2026-04-21",
    }, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["tipo"] == "iva"
    assert data["estado"] == "pendiente"


def test_listar_vencimientos_por_cliente(client, auth_headers, vencimiento_test):
    response = client.get(
        f"/api/vencimientos?cliente_id={vencimiento_test.cliente_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_obtener_vencimiento(client, auth_headers, vencimiento_test):
    response = client.get(
        f"/api/vencimientos/{vencimiento_test.id}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == vencimiento_test.id


def test_actualizar_estado_vencimiento(client, auth_headers, vencimiento_test):
    response = client.put(
        f"/api/vencimientos/{vencimiento_test.id}",
        json={"estado": "cumplido", "fecha_cumplimiento": "2026-03-20"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["estado"] == "cumplido"


def test_vencimiento_inexistente(client, auth_headers):
    response = client.get("/api/vencimientos/99999", headers=auth_headers)
    assert response.status_code == 404
