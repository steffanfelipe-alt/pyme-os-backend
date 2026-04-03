def test_register_exitoso(client):
    response = client.post("/api/auth/register", json={
        "email": "nuevo@test.com",
        "password": "pass123",
        "nombre": "Usuario Nuevo",
    })
    assert response.status_code == 201
    assert "access_token" in response.json()


def test_register_email_duplicado(client):
    datos = {"email": "dup@test.com", "password": "pass123", "nombre": "A"}
    client.post("/api/auth/register", json=datos)
    response = client.post("/api/auth/register", json=datos)
    assert response.status_code == 409


def test_login_exitoso(client):
    client.post("/api/auth/register", json={
        "email": "login@test.com", "password": "pass123", "nombre": "B"
    })
    response = client.post("/api/auth/login", json={
        "email": "login@test.com", "password": "pass123"
    })
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_login_credenciales_incorrectas(client):
    response = client.post("/api/auth/login", json={
        "email": "noexiste@test.com", "password": "wrong"
    })
    assert response.status_code == 401


def test_endpoint_protegido_sin_token(client):
    response = client.get("/api/clientes")
    # HTTPBearer devuelve 403 cuando no hay credenciales (comportamiento de FastAPI)
    assert response.status_code in (401, 403)
