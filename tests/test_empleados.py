def test_crear_empleado(client, auth_headers):
    response = client.post("/api/empleados", json={
        "nombre": "María López",
        "email": "maria@estudio.com",
        "rol": "contador",
    }, headers=auth_headers)
    assert response.status_code == 201
    assert response.json()["nombre"] == "María López"


def test_crear_empleado_email_duplicado(client, auth_headers, empleado_test):
    response = client.post("/api/empleados", json={
        "nombre": "Otro",
        "email": empleado_test.email,
        "rol": "contador",
    }, headers=auth_headers)
    assert response.status_code == 409


def test_listar_empleados(client, auth_headers, empleado_test):
    response = client.get("/api/empleados", headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json()) >= 1


def test_obtener_empleado(client, auth_headers, empleado_test):
    response = client.get(
        f"/api/empleados/{empleado_test.id}", headers=auth_headers
    )
    assert response.status_code == 200
    assert response.json()["id"] == empleado_test.id


def test_actualizar_empleado(client, auth_headers, empleado_test):
    response = client.put(
        f"/api/empleados/{empleado_test.id}",
        json={"nombre": "Lucas García Actualizado"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["nombre"] == "Lucas García Actualizado"
