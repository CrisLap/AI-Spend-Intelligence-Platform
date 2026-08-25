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


def test_same_role_user_can_see_and_correct_shared_line_item(client: TestClient):
    """Spend data is now shared per role: two buyers see and can correct
    each other's line items (only chat/agent-run history stays private)."""
    _, owner_headers = _register_and_login(client, "owner@spend.com")
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("t.csv", csv, "text/csv")}, headers=owner_headers)
    doc_id = r.json()["id"]
    r = client.post(f"/documents/{doc_id}/process", headers=owner_headers)
    item_id = r.json()["line_items"][0]["id"]

    _, teammate_headers = _register_and_login(client, "teammate@spend.com")
    r = client.get(f"/documents/{doc_id}", headers=teammate_headers)
    assert r.status_code == 200

    r = client.patch(
        f"/classification/line-items/{item_id}",
        json={"category_label": "Office Equipment & Supplies"},
        headers=teammate_headers,
    )
    assert r.status_code == 200
    assert r.json()["category_label"] == "Office Equipment & Supplies"


def test_different_role_user_cannot_see_line_item(client: TestClient):
    """A buyer's document must stay invisible to a finance-role user."""
    _, buyer_headers = _register_and_login(client, "buyer-owner@spend.com")
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("t.csv", csv, "text/csv")}, headers=buyer_headers)
    doc_id = r.json()["id"]
    r = client.post(f"/documents/{doc_id}/process", headers=buyer_headers)
    item_id = r.json()["line_items"][0]["id"]

    _, finance_headers = _register_and_login(client, "finance-outsider@spend.com", role_attempt="finance")
    r = client.get(f"/documents/{doc_id}", headers=finance_headers)
    assert r.status_code == 404
    r = client.patch(
        f"/classification/line-items/{item_id}",
        json={"category_label": "Hacked"},
        headers=finance_headers,
    )
    assert r.status_code == 404


def test_admin_sees_documents_of_any_role(client: TestClient, auth_headers: dict):
    _, buyer_headers = _register_and_login(client, "buyer-for-admin@spend.com")
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("t.csv", csv, "text/csv")}, headers=buyer_headers)
    doc_id = r.json()["id"]
    client.post(f"/documents/{doc_id}/process", headers=buyer_headers)

    r = client.get(f"/documents/{doc_id}", headers=auth_headers)
    assert r.status_code == 200


def test_promoting_a_second_admin_demotes_the_first(client: TestClient, auth_headers: dict):
    # auth_headers wraps the shared seed admin ("test@spend.com" from
    # conftest.py), reused across the whole test session - this test
    # restores it back to admin at the end so later tests relying on
    # auth_headers being admin aren't left broken (the SQLite test DB
    # persists across the whole session, not per-test).
    original_admin_id = client.get("/auth/me", headers=auth_headers).json()["id"]
    _, buyer_headers = _register_and_login(client, "future-admin@spend.com")
    new_admin_id = client.get("/auth/me", headers=buyer_headers).json()["id"]

    r = client.patch(f"/users/{new_admin_id}/role", json={"role": "admin"}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    r = client.get(f"/users/{original_admin_id}/audit-log", headers=buyer_headers)
    assert r.status_code == 200  # the new admin can now use admin-only endpoints

    users_list = client.get("/users", headers=buyer_headers).json()
    original = next(u for u in users_list if u["id"] == original_admin_id)
    assert original["role"] == "buyer"

    restore = client.patch(f"/users/{original_admin_id}/role", json={"role": "admin"}, headers=buyer_headers)
    assert restore.status_code == 200
    assert restore.json()["role"] == "admin"


def test_admin_cannot_demote_their_own_role(client: TestClient, auth_headers: dict):
    """Self-demotion would leave the system with zero admins and no way to
    recover via the API (every admin-only endpoint, including this one,
    requires an admin) - must be rejected, mirroring delete_user's guard
    against self-deletion."""
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["role"] == "admin"

    r = client.patch(f"/users/{me['id']}/role", json={"role": "buyer"}, headers=auth_headers)
    assert r.status_code == 400

    r = client.get("/auth/me", headers=auth_headers)
    assert r.json()["role"] == "admin"


def test_register_can_choose_finance_but_not_admin(client: TestClient):
    _, finance_headers = _register_and_login(client, "self-finance@spend.com", role_attempt="finance")
    r = client.get("/auth/me", headers=finance_headers)
    assert r.json()["role"] == "finance"

    _, wannabe_headers = _register_and_login(client, "self-admin@spend.com", role_attempt="admin")
    r = client.get("/auth/me", headers=wannabe_headers)
    assert r.json()["role"] == "buyer"


def test_audit_log_records_login_and_admin_can_view_it(client: TestClient, auth_headers: dict):
    me = client.get("/auth/me", headers=auth_headers).json()
    r = client.get(f"/users/{me['id']}/audit-log", headers=auth_headers)
    assert r.status_code == 200
    actions = [entry["action"] for entry in r.json()]
    assert "login" in actions
