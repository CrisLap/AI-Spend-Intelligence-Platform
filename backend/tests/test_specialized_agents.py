from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.models.document import DocType, Document, LineItem
from app.models.user import User
from app.services import contract_intelligence, cost_saving_agent


def _make_user(db, email: str) -> User:
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_item(db, owner: User, total: float, created_at) -> None:
    doc = Document(user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.add(LineItem(document_id=doc.id, description="item", total=total, created_at=created_at))
    db.commit()


def _make_contract_with_risk_clause(db, owner: User) -> Document:
    doc = Document(
        user_id=owner.id, filename="risky.txt", original_name="risky.txt", file_path="/tmp/risky.txt",
        doc_type=DocType.contract,
        raw_text=(
            "PENALE RECESSO ANTICIPATO: in caso di recesso anticipato dal cliente "
            "e' prevista una penale (penale recesso anticipato) pari al 30% del valore residuo."
        ),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# --- Forecast Agent -----------------------------------------------------


def test_forecast_recommendations_reflect_a_real_trend(db):
    owner = _make_user(db, "forecastagent@test.com")
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    for i, total in enumerate([100.0, 200.0, 300.0, 400.0]):
        _make_item(db, owner, total, base + dt.timedelta(days=31 * i))

    recs = cost_saving_agent._forecast_recommendations(owner.id, db)

    assert len(recs) == 1
    assert recs[0]["estimated_saving"] is None  # a forecast isn't a saving figure
    assert "500" in recs[0]["reason"] or "500,00" in recs[0]["reason"]
    # the chart payload carries the same real numbers the text reason is
    # built from, for the frontend's ForecastChart - not a second,
    # independently-computed figure that could drift from the text.
    chart = recs[0]["chart"]
    assert chart["months"] == ["2026-01", "2026-02", "2026-03", "2026-04"]
    assert chart["monthly_totals"] == [100.0, 200.0, 300.0, 400.0]
    assert chart["forecast_next_month"] == 500.0


def test_forecast_recommendations_empty_without_enough_history(db):
    owner = _make_user(db, "forecastagentempty@test.com")
    _make_item(db, owner, 100.0, dt.datetime(2026, 1, 1, tzinfo=dt.UTC))

    assert cost_saving_agent._forecast_recommendations(owner.id, db) == []


def test_analyze_forecast_agent_persists_a_run(db, monkeypatch):
    monkeypatch.setattr(
        cost_saving_agent, "chat_with_tools",
        lambda messages, tools: {"content": "Thought: ok.\nFinal Answer: Forecast checked.", "tool_calls": None},
    )
    owner = _make_user(db, "forecastanalyze@test.com")
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    for i, total in enumerate([100.0, 200.0, 300.0, 400.0]):
        _make_item(db, owner, total, base + dt.timedelta(days=31 * i))

    run = cost_saving_agent.analyze("Prevedi la spesa futura", owner.id, db, agent_type="forecast")

    assert run.agent_type == "forecast"
    assert run.summary == "Forecast checked."


# --- Contract Risk Agent -------------------------------------------------


def test_contract_risk_recommendations_use_real_contract_search(db, monkeypatch):
    monkeypatch.setattr(contract_intelligence, "qdrant_search_contracts", lambda *a, **kw: None)
    monkeypatch.setattr(contract_intelligence, "upsert_contract_chunk", lambda *a, **kw: False)
    owner = _make_user(db, "riskagent@test.com")
    doc = _make_contract_with_risk_clause(db, owner)
    contract_intelligence.index_contract(doc, db)

    recs = cost_saving_agent._contract_risk_recommendations(owner.id, db)

    assert len(recs) >= 1
    assert all(r["estimated_saving"] is None for r in recs)
    assert any("penale" in r["reason"].lower() for r in recs)


def test_analyze_contract_risk_agent_persists_a_run(db, monkeypatch):
    monkeypatch.setattr(
        cost_saving_agent, "chat_with_tools",
        lambda messages, tools: {"content": "Thought: ok.\nFinal Answer: Risk checked.", "tool_calls": None},
    )
    owner = _make_user(db, "riskanalyze@test.com")

    run = cost_saving_agent.analyze("Verifica i rischi contrattuali", owner.id, db, agent_type="contract_risk")

    assert run.agent_type == "contract_risk"
    assert run.summary == "Risk checked."


# --- API: agent_type plumbing --------------------------------------------


def test_analyze_endpoint_accepts_agent_type(client: TestClient, auth_headers: dict):
    r = client.post(
        "/cost-saving/analyze", json={"goal": "Prevedi la spesa futura", "agent_type": "forecast"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["agent_type"] == "forecast"


def test_analyze_endpoint_rejects_an_unknown_agent_type(client: TestClient, auth_headers: dict):
    r = client.post(
        "/cost-saving/analyze", json={"goal": "x", "agent_type": "not_a_real_agent"}, headers=auth_headers
    )
    assert r.status_code == 400


def test_history_can_be_filtered_by_agent_type(client: TestClient, auth_headers: dict):
    client.post("/cost-saving/analyze", json={"goal": "cost saving run", "agent_type": "cost_saving"}, headers=auth_headers)
    client.post("/cost-saving/analyze", json={"goal": "forecast run", "agent_type": "forecast"}, headers=auth_headers)

    r = client.get("/cost-saving/history", params={"agent_type": "forecast"}, headers=auth_headers)
    assert r.status_code == 200
    goals = [run["goal"] for run in r.json()]
    assert "forecast run" in goals
    assert "cost saving run" not in goals
