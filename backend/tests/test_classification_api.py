from fastapi.testclient import TestClient


def test_classify_descriptions(client: TestClient, auth_headers: dict):
    r = client.post("/classification", json={"descriptions": ["HP LaserJet Toner", "Consulenza legale"]}, headers=auth_headers)
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 2
    assert results[0]["category"] == "Office Equipment & Supplies"


def test_search_endpoint(client: TestClient, auth_headers: dict):
    r = client.get("/search?q=toner&top_k=5", headers=auth_headers)
    assert r.status_code == 200
