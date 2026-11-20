from fastapi.testclient import TestClient

from app.core import login_throttle


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


def test_login_locks_account_after_repeated_failures(client: TestClient):
    # Even the correct password is refused once the account is locked, and
    # the lock is per account: another email is unaffected.
    for _ in range(login_throttle.MAX_FAILURES):
        r = client.post("/auth/login", json={"email": "test@spend.com", "password": "wrong-password"})
        assert r.status_code == 401
    locked = client.post("/auth/login", json={"email": "test@spend.com", "password": "test123"})
    assert locked.status_code == 429
    other = client.post("/auth/login", json={"email": "other@spend.com", "password": "wrong-password"})
    assert other.status_code == 401


def test_successful_login_clears_failure_count(client: TestClient):
    for _ in range(login_throttle.MAX_FAILURES - 1):
        client.post("/auth/login", json={"email": "test@spend.com", "password": "wrong-password"})
    assert client.post("/auth/login", json={"email": "test@spend.com", "password": "test123"}).status_code == 200
    for _ in range(login_throttle.MAX_FAILURES - 1):
        client.post("/auth/login", json={"email": "test@spend.com", "password": "wrong-password"})
    assert client.post("/auth/login", json={"email": "test@spend.com", "password": "test123"}).status_code == 200


def test_security_headers_present(client: TestClient):
    r = client.get("/health")
    assert r.json() == {"status": "ok"}
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    # Swagger UI needs to load its assets, so the strict CSP skips the docs pages.
    assert "Content-Security-Policy" not in client.get("/docs").headers
