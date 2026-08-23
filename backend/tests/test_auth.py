from fastapi.testclient import TestClient


def test_register(client: TestClient):
    r = client.post(
        "/auth/register", json={"email": "new@user.com", "password": "a-strong-passw0rd", "full_name": "New User"}
    )
    assert r.status_code == 201
    assert "access_token" in r.json()


def test_register_rejects_weak_password(client: TestClient):
    r = client.post("/auth/register", json={"email": "weak@user.com", "password": "short", "full_name": "Weak User"})
    assert r.status_code == 422


def test_login(client: TestClient):
    r = client.post("/auth/login", json={"email": "test@spend.com", "password": "test123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_me(client: TestClient, token: str):
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "test@spend.com"


def test_disabled_user_token_is_rejected(client: TestClient, token: str, db):
    from app.models.user import User
    user = db.query(User).filter(User.email == "test@spend.com").first()
    user.is_active = False
    db.commit()
    try:
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401
    finally:
        user.is_active = True
        db.commit()


def test_login_invalid(client: TestClient):
    r = client.post("/auth/login", json={"email": "no@no.com", "password": "wrong"})
    assert r.status_code == 401
