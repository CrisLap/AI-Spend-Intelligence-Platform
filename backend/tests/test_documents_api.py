from fastapi.testclient import TestClient


def test_upload_csv(client: TestClient, auth_headers: dict):
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot\nCarta A4,5,12.00,60.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("test.csv", csv, "text/csv")}, headers=auth_headers)
    assert r.status_code == 201
    assert r.json()["status"] == "processing"


def test_upload_and_process(client: TestClient, auth_headers: dict):
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot\nCarta A4,5,12.00,60.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("test.csv", csv, "text/csv")}, headers=auth_headers)
    doc_id = r.json()["id"]

    r = client.post(f"/documents/{doc_id}/process", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["line_items"]) == 2
    assert data["line_items"][0]["description"] == "Toner HP"


def test_list_documents(client: TestClient, auth_headers: dict):
    r = client.get("/documents", headers=auth_headers)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_upload_rejects_unsupported_extension(client: TestClient, auth_headers: dict):
    r = client.post(
        "/documents/upload",
        files={"file": ("script.exe", b"MZ...", "application/octet-stream")},
        headers=auth_headers,
    )
    assert r.status_code == 415


def test_upload_rejects_oversized_file(client: TestClient, auth_headers: dict, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "max_upload_mb", 0)  # anything is "too big" now
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot"
    r = client.post(
        "/documents/upload",
        files={"file": ("big.csv", csv, "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 413
