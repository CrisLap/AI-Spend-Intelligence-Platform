from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.services import cost_saving_agent


def test_analyze_stream_yields_one_step_event_per_step_then_a_done_event(db, monkeypatch):
    """Service-level check that analyze_stream() is a real generator
    yielding incrementally, not a batch result wrapped to look like one -
    each chunk must already be well-formed SSE (event + data) as it's
    produced, and the trailing `done` event must carry the full persisted
    run (recommendations included), same shape POST /analyze returns."""
    calls = {"n": 0}

    def fake_chat_with_tools(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": None,
                "tool_calls": [{"function": {"name": "spend_overview", "arguments": '{"input": "overview"}'}}],
            }
        return {"content": "Thought: done.\nFinal Answer: All checked.", "tool_calls": None}

    monkeypatch.setattr(cost_saving_agent, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(cost_saving_agent, "get_supplier_variance", lambda **kw: [])
    monkeypatch.setattr(cost_saving_agent, "search_contracts", lambda *a, **kw: [])

    chunks = list(cost_saving_agent.analyze_stream("Trova opportunità di risparmio", user_id=1, db=db))

    step_chunks = [c for c in chunks if c.startswith("event: step")]
    done_chunks = [c for c in chunks if c.startswith("event: done")]

    assert len(step_chunks) == 2  # one tool-call step, one final-answer step
    assert len(done_chunks) == 1
    assert chunks[-1] == done_chunks[0]  # done is always last

    first_step_payload = json.loads(step_chunks[0].split("data: ", 1)[1])
    assert first_step_payload["tool"] == "spend_overview"
    assert first_step_payload["mode"] == "structured"

    done_payload = json.loads(done_chunks[0].split("data: ", 1)[1])
    assert done_payload["summary"] == "All checked."
    assert "id" in done_payload
    assert done_payload["recommendations"] == []


def test_analyze_stream_endpoint_returns_event_stream_with_a_terminal_done_event(client: TestClient, auth_headers: dict):
    with client.stream(
        "GET", "/cost-saving/analyze/stream", params={"goal": "Trova opportunità di risparmio"}, headers=auth_headers
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = "".join(r.iter_text())

    assert "event: done" in body
    assert body.rstrip().endswith("}")  # the done event's JSON is the last thing streamed


def test_analyze_stream_requires_authentication(client: TestClient):
    r = client.get("/cost-saving/analyze/stream")
    assert r.status_code == 401
