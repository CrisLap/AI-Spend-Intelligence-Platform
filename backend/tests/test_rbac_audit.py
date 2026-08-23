from __future__ import annotations

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str, role_attempt: str | None = None) -> tuple[str, dict]:
    payload = {"email": email, "password": "pass1234567", "full_name": "Test"}
    if role_attempt:
        payload["role"] = role_attempt
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201
    token = r.json()["access_token"]
    return token, {"Authorization": f"Bearer {token}"}


def test_register_ignores_requested_role(client: TestClient):
    _, headers = _register_and_login(client, "wannabe-admin@spend.com", role_attempt="admin")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["role"] == "buyer"


def test_list_users_forbidden_for_buyer(client: TestClient):
    _, buyer_headers = _register_and_login(client, "buyer1@spend.com")
    r = client.get("/users", headers=buyer_headers)
    assert r.status_code == 403


def test_list_users_allowed_for_admin(client: TestClient, auth_headers: dict):
    r = client.get("/users", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_update_user_role_admin_only(client: TestClient, auth_headers: dict):
    _, buyer_headers = _register_and_login(client, "buyer2@spend.com")
    me = client.get("/auth/me", headers=buyer_headers).json()

    denied = client.patch(f"/users/{me['id']}/role", json={"role": "finance"}, headers=buyer_headers)
    assert denied.status_code == 403

    allowed = client.patch(f"/users/{me['id']}/role", json={"role": "finance"}, headers=auth_headers)
    assert allowed.status_code == 200
    assert allowed.json()["role"] == "finance"


def test_retrain_forbidden_for_buyer(client: TestClient):
    _, buyer_headers = _register_and_login(client, "buyer3@spend.com")
    r = client.post("/classification/retrain", headers=buyer_headers)
    assert r.status_code == 403


def test_retrain_allowed_for_admin(client: TestClient, auth_headers: dict):
    r = client.post("/classification/retrain", headers=auth_headers)
    assert r.status_code == 200


def test_cannot_correct_another_users_line_item(client: TestClient):
    _, owner_headers = _register_and_login(client, "owner@spend.com")
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("t.csv", csv, "text/csv")}, headers=owner_headers)
    doc_id = r.json()["id"]
    r = client.post(f"/documents/{doc_id}/process", headers=owner_headers)
    item_id = r.json()["line_items"][0]["id"]

    _, intruder_headers = _register_and_login(client, "intruder@spend.com")
    r = client.patch(
        f"/classification/line-items/{item_id}",
        json={"category_label": "Hacked"},
        headers=intruder_headers,
    )
    assert r.status_code == 404


def test_audit_log_records_login_and_admin_can_view_it(client: TestClient, auth_headers: dict):
    me = client.get("/auth/me", headers=auth_headers).json()
    r = client.get(f"/users/{me['id']}/audit-log", headers=auth_headers)
    assert r.status_code == 200
    actions = [entry["action"] for entry in r.json()]
    assert "login" in actions
