from __future__ import annotations

from fastapi.testclient import TestClient


def test_analyze_returns_a_run_with_steps_and_recommendations(client: TestClient, auth_headers: dict):
    r = client.post("/cost-saving/analyze", json={"goal": "Trova opportunità di risparmio"}, headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["goal"] == "Trova opportunità di risparmio"
    assert isinstance(data["steps"], list)
    assert isinstance(data["recommendations"], list)
    assert "id" in data


def test_analyze_uses_the_default_goal_when_none_given(client: TestClient, auth_headers: dict):
    r = client.post("/cost-saving/analyze", json={}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["goal"]


def test_analyze_requires_authentication(client: TestClient):
    r = client.post("/cost-saving/analyze", json={"goal": "test"})
    assert r.status_code == 401


def test_history_lists_previous_runs_for_the_current_user(client: TestClient, auth_headers: dict):
    client.post("/cost-saving/analyze", json={"goal": "Run 1"}, headers=auth_headers)
    client.post("/cost-saving/analyze", json={"goal": "Run 2"}, headers=auth_headers)

    r = client.get("/cost-saving/history", headers=auth_headers)
    assert r.status_code == 200
    goals = [run["goal"] for run in r.json()]
    assert "Run 1" in goals
    assert "Run 2" in goals


def test_history_run_not_found_returns_404(client: TestClient, auth_headers: dict):
    r = client.get("/cost-saving/history/999999", headers=auth_headers)
    assert r.status_code == 404


def test_history_run_owned_by_another_user_is_not_visible(client: TestClient, auth_headers: dict, db):
    from app.core.security import hash_password
    from app.models.agent_run import AgentRun
    from app.models.user import User

    other = User(email="othercostsaving@test.com", hashed_password=hash_password("x"), full_name="Other", role="buyer")
    db.add(other)
    db.commit()
    db.refresh(other)
    run = AgentRun(user_id=other.id, goal="Someone else's run", steps_json="[]", recommendations_json="[]", summary="x")
    db.add(run)
    db.commit()
    db.refresh(run)

    r = client.get(f"/cost-saving/history/{run.id}", headers=auth_headers)
    assert r.status_code == 404
