from __future__ import annotations

from fastapi.testclient import TestClient

from app.services import assistant_router, chat_service
from tests.conftest import TestSessionLocal

# --- classify_intent: rule-based tier, at least 5 representative messages
# (3 spend questions, 2 cost-saving goals), per the Fase 2 plan's own
# verification checklist for F2.3. ---------------------------------------


def test_classifies_a_spend_amount_question_as_chat():
    result = assistant_router.classify_intent("Quanto abbiamo speso in consulenza quest'anno?")
    assert result["intent"] == "chat"
    assert result["agent_type"] is None


def test_classifies_a_supplier_listing_question_as_chat():
    result = assistant_router.classify_intent("Mostrami quali fornitori abbiamo usato per l'IT")
    assert result["intent"] == "chat"


def test_classifies_an_english_spend_question_as_chat():
    result = assistant_router.classify_intent("How much did we spend on software licenses?")
    assert result["intent"] == "chat"


def test_classifies_a_saving_goal_as_cost_saving_agent_type():
    result = assistant_router.classify_intent("Trova opportunità di risparmio nei nostri contratti")
    assert result["intent"] == "cost_saving"
    assert result["agent_type"] == "cost_saving"


def test_classifies_a_forecast_goal_as_forecast_agent_type():
    result = assistant_router.classify_intent("Prevedi la spesa del prossimo mese")
    assert result["intent"] == "cost_saving"
    assert result["agent_type"] == "forecast"


def test_classifies_a_contract_risk_goal_as_contract_risk_agent_type():
    result = assistant_router.classify_intent("Verifica se ci sono clausole di penale nei contratti")
    assert result["intent"] == "cost_saving"
    assert result["agent_type"] == "contract_risk"


def test_falls_back_to_chat_for_an_unmatched_message_offline(monkeypatch):
    # No keyword hits and the LLM call fails offline (no provider reachable
    # in tests) -> must default to "chat", never crash.
    result = assistant_router.classify_intent("asdkjhasdkjh")
    assert result["intent"] == "chat"
    assert result["method"] == "default"


def test_llm_tier_is_used_when_no_keyword_matches(monkeypatch):
    monkeypatch.setattr(
        assistant_router, "chat",
        lambda messages: '{"intent": "cost_saving", "agent_type": "forecast"}',
    )
    result = assistant_router.classify_intent("cosa mi consigli di fare con i numeri di domani")
    assert result == {"intent": "cost_saving", "agent_type": "forecast", "confidence": 0.6, "method": "llm"}


# --- API: /assistant routes correctly to each branch ---------------------


def test_assistant_endpoint_routes_a_spend_question_to_chat(client: TestClient, auth_headers: dict, monkeypatch):
    monkeypatch.setattr(chat_service, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(chat_service, "qdrant_search", lambda *a, **kw: [])
    monkeypatch.setattr("app.services.ai.chat", lambda messages: "Final Answer: Abbiamo speso 1000 euro.")

    r = client.post("/assistant", json={"message": "Quanto abbiamo speso in totale?"}, headers=auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "chat"
    assert body["chat"] is not None
    assert body["suggestion"] is None
    assert "session_id" in body["chat"]


def test_assistant_endpoint_routes_a_saving_goal_to_a_suggestion(client: TestClient, auth_headers: dict):
    r = client.post(
        "/assistant", json={"message": "Trova opportunità di risparmio sui fornitori"}, headers=auth_headers
    )

    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "cost_saving"
    assert body["chat"] is None
    assert body["suggestion"]["agent_type"] == "cost_saving"
    assert body["suggestion"]["goal"] == "Trova opportunità di risparmio sui fornitori"


def test_assistant_endpoint_routes_a_forecast_goal_with_the_forecast_agent_type(
    client: TestClient, auth_headers: dict
):
    r = client.post("/assistant", json={"message": "Prevedi la spesa futura"}, headers=auth_headers)

    assert r.status_code == 200
    assert r.json()["suggestion"]["agent_type"] == "forecast"


# --- API: GET /assistant/stream (SSE equivalent) --------------------------


def test_assistant_stream_endpoint_streams_a_terminal_done_event_for_a_chat_message(
    client: TestClient, auth_headers: dict, monkeypatch
):
    monkeypatch.setattr(chat_service, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(chat_service, "qdrant_search", lambda *a, **kw: [])
    monkeypatch.setattr("app.services.ai.chat", lambda messages: "Final Answer: Abbiamo speso 1000 euro.")

    with client.stream(
        "GET", "/assistant/stream", params={"message": "Quanto abbiamo speso in totale?"}, headers=auth_headers
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = "".join(r.iter_text())

    assert "event: done" in body
    assert body.rstrip().endswith("}")


def test_assistant_stream_endpoint_streams_a_suggestion_event_for_a_saving_goal(
    client: TestClient, auth_headers: dict
):
    with client.stream(
        "GET", "/assistant/stream", params={"message": "Trova opportunità di risparmio sui fornitori"},
        headers=auth_headers,
    ) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())

    assert "event: suggestion" in body
    assert "cost_saving" in body


def test_assistant_stream_requires_authentication(client: TestClient):
    r = client.get("/assistant/stream", params={"message": "x"})
    assert r.status_code == 401
