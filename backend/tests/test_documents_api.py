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


def test_reprocessing_a_document_replaces_line_items_instead_of_duplicating(client: TestClient, auth_headers: dict):
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot\nCarta A4,5,12.00,60.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("reproc.csv", csv, "text/csv")}, headers=auth_headers)
    doc_id = r.json()["id"]

    r1 = client.post(f"/documents/{doc_id}/process", headers=auth_headers)
    assert len(r1.json()["line_items"]) == 2

    r2 = client.post(f"/documents/{doc_id}/process", headers=auth_headers)
    assert len(r2.json()["line_items"]) == 2  # not 4 - old items must be replaced, not piled on


def test_deleting_a_processed_document_does_not_violate_foreign_keys(client: TestClient, auth_headers: dict):
    """Deleting a document that already has line items (and therefore
    possibly duplicate groups) used to fail with a foreign key violation
    on Postgres, since dependents were never cleaned up first."""
    csv = b"description,quantity,unit_price,total,supplier\nToner HP,2,90.00,180.00,Office Depot"
    r = client.post("/documents/upload", files={"file": ("todelete.csv", csv, "text/csv")}, headers=auth_headers)
    doc_id = r.json()["id"]
    client.post(f"/documents/{doc_id}/process", headers=auth_headers)

    r = client.delete(f"/documents/{doc_id}", headers=auth_headers)
    assert r.status_code == 204


def test_duplicate_similarity_threshold_setting_is_actually_used(client: TestClient, auth_headers: dict, monkeypatch):
    """settings.duplicate_similarity_threshold used to be defined but never
    read - find_duplicates always used its own hardcoded default instead."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "duplicate_similarity_threshold", 0.999)

    csv = (
        b"description,quantity,unit_price,total,supplier\n"
        b"Toner cartridge HP LaserJet 415A black,1,50.00,50.00,Office Depot\n"
        b"Toner cartridge HP LaserJet 415A colour,1,50.00,50.00,Office Depot"
    )
    r = client.post("/documents/upload", files={"file": ("thresh.csv", csv, "text/csv")}, headers=auth_headers)
    doc_id = r.json()["id"]
    client.post(f"/documents/{doc_id}/process", headers=auth_headers)

    r = client.get("/duplicates", headers=auth_headers)
    ids_in_groups = {item["id"] for g in r.json() for item in g["items"]}
    doc_items = client.get(f"/documents/{doc_id}", headers=auth_headers).json()["line_items"]
    # With an almost-impossible 0.999 threshold, these two merely-similar
    # (not identical) descriptions must NOT be grouped as duplicates.
    assert not any(i["id"] in ids_in_groups for i in doc_items)
