def test_crear_cliente(client, auth_headers):
    response = client.post("/api/clientes", json={
        "tipo_persona": "juridica",
        "nombre": "García SA",
        "cuit_cuil": "30-98765432-1",
        "condicion_fiscal": "responsable_inscripto",
    }, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["nombre"] == "García SA"
    assert data["cuit_cuil"] == "30-98765432-1"


def test_crear_cliente_cuit_duplicado(client, auth_headers, cliente_test):
    response = client.post("/api/clientes", json={
        "tipo_persona": "juridica",
        "nombre": "Otro",
        "cuit_cuil": cliente_test.cuit_cuil,
        "condicion_fiscal": "responsable_inscripto",
    }, headers=auth_headers)
    assert response.status_code == 409


def test_listar_clientes(client, auth_headers, cliente_test):
    response = client.get("/api/clientes", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_obtener_cliente(client, auth_headers, cliente_test):
    response = client.get(
        f"/api/clientes/{cliente_test.id}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == cliente_test.id


def test_obtener_cliente_inexistente(client, auth_headers):
    response = client.get("/api/clientes/99999", headers=auth_headers)
    assert response.status_code == 404


def test_actualizar_cliente(client, auth_headers, cliente_test):
    response = client.put(
        f"/api/clientes/{cliente_test.id}",
        json={"nombre": "Martínez SRL Actualizado"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["nombre"] == "Martínez SRL Actualizado"


def test_eliminar_cliente(client, auth_headers, cliente_test):
    response = client.delete(
        f"/api/clientes/{cliente_test.id}", headers=auth_headers
    )
    assert response.status_code == 204
