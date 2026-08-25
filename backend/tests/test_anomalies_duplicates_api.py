from __future__ import annotations

from fastapi.testclient import TestClient


def _register_and_login(client: TestClient, email: str) -> dict:
    payload = {"email": email, "password": "pass1234567", "full_name": "Test"}
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201
    token = r.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload_and_process(client: TestClient, headers: dict, csv: bytes) -> int:
    r = client.post("/documents/upload", files={"file": ("t.csv", csv, "text/csv")}, headers=headers)
    doc_id = r.json()["id"]
    client.post(f"/documents/{doc_id}/process", headers=headers)
    return doc_id


def _my_item_ids(client: TestClient, headers: dict, doc_id: int) -> set[int]:
    """Line item ids belonging to this test's own uploaded document - spend
    data (anomalies/duplicates) is now shared per role, so a test whose
    default-role user shares a pool with every other default-role test in
    this session can't assume it's the only/first entry in a list response;
    it must pick out its own item(s) explicitly."""
    items = client.get(f"/documents/{doc_id}", headers=headers).json()["line_items"]
    return {i["id"] for i in items}


def _anomaly_csv() -> bytes:
    rows = [b"description,quantity,unit_price,total,supplier"]
    for _ in range(10):
        rows.append(b"Widget A,1,10.00,10.00,Supplier X")
    rows.append(b"Widget A,1,10000.00,10000.00,Supplier X")
    return b"\n".join(rows)


def _duplicate_csv() -> bytes:
    return (
        b"description,quantity,unit_price,total,supplier\n"
        b"Toner cartridge HP LaserJet 415A black,1,50.00,50.00,Office Depot\n"
        b"Toner cartridge HP LaserJet 415A black,1,50.00,50.00,Office Depot"
    )


def test_anomaly_lifecycle_resolve_filter_search(client: TestClient):
    headers = _register_and_login(client, "anom-owner@spend.com")
    doc_id = _upload_and_process(client, headers, _anomaly_csv())
    my_item_ids = _my_item_ids(client, headers, doc_id)

    r = client.get("/anomalies", headers=headers)
    assert r.status_code == 200
    anomalies = r.json()
    flagged = next(a for a in anomalies if a["id"] in my_item_ids)
    assert flagged["resolved"] is False

    # search matches, unrelated search term does not
    r = client.get("/anomalies", params={"search": "Widget"}, headers=headers)
    assert any(a["id"] == flagged["id"] for a in r.json())
    r = client.get("/anomalies", params={"search": "no-such-term"}, headers=headers)
    assert r.json() == []

    # resolve, then it disappears from the default (unresolved-only) list
    r = client.patch(f"/anomalies/{flagged['id']}/resolve", json={"resolved": True}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"id": flagged["id"], "resolved": True}

    r = client.get("/anomalies", headers=headers)
    assert flagged["id"] not in [a["id"] for a in r.json()]

    r = client.get("/anomalies", params={"include_resolved": True}, headers=headers)
    resolved_ids = {a["id"]: a["resolved"] for a in r.json()}
    assert resolved_ids[flagged["id"]] is True

    # unresolve brings it back
    r = client.patch(f"/anomalies/{flagged['id']}/resolve", json={"resolved": False}, headers=headers)
    assert r.json()["resolved"] is False
    r = client.get("/anomalies", headers=headers)
    assert flagged["id"] in [a["id"] for a in r.json()]


def test_same_role_user_can_resolve_shared_anomaly(client: TestClient):
    """Spend data (including anomalies) is shared per role: a same-role
    teammate can resolve an anomaly they didn't personally upload."""
    owner_headers = _register_and_login(client, "anom-owner2@spend.com")
    doc_id = _upload_and_process(client, owner_headers, _anomaly_csv())
    my_item_ids = _my_item_ids(client, owner_headers, doc_id)
    anomalies = client.get("/anomalies", headers=owner_headers).json()
    flagged_id = next(a for a in anomalies if a["id"] in my_item_ids)["id"]

    teammate_headers = _register_and_login(client, "anom-teammate@spend.com")
    r = client.patch(f"/anomalies/{flagged_id}/resolve", json={"resolved": True}, headers=teammate_headers)
    assert r.status_code == 200


def test_duplicate_lifecycle_resolve_filter_search(client: TestClient):
    headers = _register_and_login(client, "dup-owner@spend.com")
    doc_id = _upload_and_process(client, headers, _duplicate_csv())
    my_item_ids = _my_item_ids(client, headers, doc_id)

    r = client.get("/duplicates", headers=headers)
    assert r.status_code == 200
    groups = r.json()
    group = next(g for g in groups if any(item["id"] in my_item_ids for item in g["items"]))
    assert group["resolved"] is False

    r = client.get("/duplicates", params={"search": "Toner"}, headers=headers)
    assert any(g["id"] == group["id"] for g in r.json())
    r = client.get("/duplicates", params={"search": "no-such-term"}, headers=headers)
    assert r.json() == []

    r = client.patch(f"/duplicates/{group['id']}/resolve", json={"resolved": True}, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"id": group["id"], "resolved": True}

    r = client.get("/duplicates", headers=headers)
    assert group["id"] not in [g["id"] for g in r.json()]

    r = client.get("/duplicates", params={"include_resolved": True}, headers=headers)
    resolved_ids = {g["id"]: g["resolved"] for g in r.json()}
    assert resolved_ids[group["id"]] is True


def test_same_role_user_can_resolve_shared_duplicate_group(client: TestClient):
    """Same as the anomaly case above: duplicate groups are shared per role."""
    owner_headers = _register_and_login(client, "dup-owner2@spend.com")
    doc_id = _upload_and_process(client, owner_headers, _duplicate_csv())
    my_item_ids = _my_item_ids(client, owner_headers, doc_id)
    groups = client.get("/duplicates", headers=owner_headers).json()
    group_id = next(g for g in groups if any(item["id"] in my_item_ids for item in g["items"]))["id"]

    teammate_headers = _register_and_login(client, "dup-teammate@spend.com")
    r = client.patch(f"/duplicates/{group_id}/resolve", json={"resolved": True}, headers=teammate_headers)
    assert r.status_code == 200


def test_documents_search_status_and_sort(client: TestClient):
    headers = _register_and_login(client, "doc-filter@spend.com")
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,1,10.00,10.00,Office Depot"
    client.post("/documents/upload", files={"file": ("alpha.csv", csv, "text/csv")}, headers=headers)
    client.post("/documents/upload", files={"file": ("beta.csv", csv, "text/csv")}, headers=headers)

    r = client.get("/documents", params={"search": "alpha"}, headers=headers)
    assert r.status_code == 200
    names = [d["original_name"] for d in r.json()]
    assert names == ["alpha.csv"]

    r = client.get("/documents", params={"status": "processing"}, headers=headers)
    assert all(d["status"] == "processing" for d in r.json())

    r = client.get("/documents", params={"sort_by": "name", "sort_dir": "asc"}, headers=headers)
    names = [d["original_name"] for d in r.json()]
    assert names == sorted(names)
