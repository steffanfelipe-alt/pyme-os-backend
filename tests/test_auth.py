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


# ---------------------------------------------------------------------------
# Forgot / Reset password
# ---------------------------------------------------------------------------

def test_forgot_password_siempre_200(client):
    """forgot-password responde 200 aunque el email no exista (no revelar info)."""
    resp = client.post("/api/auth/forgot-password", json={"email": "noexiste@test.com"})
    assert resp.status_code == 200
    assert "detail" in resp.json()


def test_forgot_password_genera_token(client, db):
    """Cuando el usuario existe, se genera un reset_token en la DB."""
    from models.usuario import Usuario
    from auth import hash_password

    usuario = Usuario(email="reset@test.com", password_hash=hash_password("old123"), nombre="Test")
    db.add(usuario)
    db.commit()
    db.refresh(usuario)

    resp = client.post("/api/auth/forgot-password", json={"email": "reset@test.com"})
    assert resp.status_code == 200

    db.refresh(usuario)
    assert usuario.reset_token is not None
    assert usuario.reset_token_expires_at is not None


def test_reset_password_exitoso(client, db):
    """Token válido → actualiza contraseña y lo invalida."""
    import secrets
    from datetime import datetime, timedelta, timezone
    from models.usuario import Usuario
    from auth import hash_password, verify_password

    token = secrets.token_urlsafe(32)
    usuario = Usuario(
        email="resetok@test.com",
        password_hash=hash_password("oldpass"),
        nombre="Reset Test",
        reset_token=token,
        reset_token_expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(usuario)
    db.commit()

    resp = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpass123"})
    assert resp.status_code == 200

    db.refresh(usuario)
    assert verify_password("newpass123", usuario.password_hash)
    assert usuario.reset_token is None
    assert usuario.reset_token_expires_at is None


def test_reset_password_token_invalido(client):
    """Token inexistente → 400."""
    resp = client.post("/api/auth/reset-password", json={"token": "inventado", "new_password": "newpass123"})
    assert resp.status_code == 400


def test_reset_password_token_expirado(client, db):
    """Token expirado → 400."""
    import secrets
    from datetime import datetime, timedelta, timezone
    from models.usuario import Usuario
    from auth import hash_password

    token = secrets.token_urlsafe(32)
    usuario = Usuario(
        email="expired@test.com",
        password_hash=hash_password("oldpass"),
        nombre="Expired Test",
        reset_token=token,
        reset_token_expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    db.add(usuario)
    db.commit()

    resp = client.post("/api/auth/reset-password", json={"token": token, "new_password": "newpass123"})
    assert resp.status_code == 400


def test_reset_password_demasiado_corta(client):
    """Contraseña menor a 8 caracteres → 422."""
    resp = client.post("/api/auth/reset-password", json={"token": "cualquiera", "new_password": "abc"})
    assert resp.status_code == 422
