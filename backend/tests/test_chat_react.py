from __future__ import annotations

from app.core.security import hash_password
from app.models.document import Document, LineItem
from app.models.user import User
from app.services import chat_react
from app.services.agents.tools import top_expenses_tool_for


def _make_user(db, email: str) -> User:
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_item(db, owner: User, description: str, supplier: str, total: float) -> None:
    doc = Document(user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.add(LineItem(document_id=doc.id, description=description, supplier=supplier, total=total))
    db.commit()


def test_direct_final_answer(monkeypatch):
    monkeypatch.setattr(
        chat_react, "chat_with_tools",
        lambda messages, tools: {
            "content": 'Thought: I have enough info.\nFinal Answer: We spent €500 on toner [Invoice-1].',
            "tool_calls": None,
        },
    )
    reply = chat_react.answer_with_react(
        message="How much on toner?",
        context=[{"text": "toner", "score": 0.9}],
    )
    assert "toner" in reply.lower()


def test_react_loop_calls_tool_then_answers(monkeypatch):
    """chat_react.py drives its ReAct loop through chat_with_tools() (not
    plain chat()) so Groq's agentic models - which attempt a real structured
    tool call for "search_spend" as soon as the system prompt describes it
    as available, even mid plain-text reply - get a valid `tools=` schema in
    the request instead of a 400 "tool_use_failed" (see chat_react.py's
    _build_react_call). This test mocks that boundary with plain-text
    content (tool_calls=None), which still exercises the regex-parsed
    Thought/Action/Observation path via react_engine's fallback."""
    calls = {"n": 0}

    def fake_chat_with_tools(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": 'Thought: need more data.\nAction: search_spend["HP toner suppliers"]',
                "tool_calls": None,
            }
        return {"content": 'Thought: now I know.\nFinal Answer: HP is the main toner supplier.', "tool_calls": None}

    monkeypatch.setattr(chat_react, "chat_with_tools", fake_chat_with_tools)

    searched = {}

    def fake_retrieve(query):
        searched["query"] = query
        return [{"text": "HP toner invoice", "score": 0.8}]

    reply = chat_react.answer_with_react(
        message="Who supplies our toner?",
        context=[],
        retrieve_fn=fake_retrieve,
    )

    assert calls["n"] == 2
    assert searched["query"] == "HP toner suppliers"
    assert "HP" in reply


def test_falls_back_to_raw_reply_when_format_not_followed(monkeypatch):
    monkeypatch.setattr(
        chat_react, "chat_with_tools",
        lambda messages, tools: {"content": "Just a plain answer with no structure.", "tool_calls": None},
    )
    reply = chat_react.answer_with_react(message="Anything?", context=[])
    assert "plain answer" in reply


def test_guardrail_blocks_sensitive_input(monkeypatch):
    monkeypatch.setattr(chat_react, "chat", lambda messages: "should not be called")
    reply = chat_react.answer_with_react(message="what is my password?", context=[])
    assert "cannot be processed" in reply


# --- answer_with_react_stream(): incremental (SSE) equivalent -----------


def test_stream_yields_one_step_per_action_then_a_final_answer(monkeypatch):
    calls = {"n": 0}

    def fake_chat_with_tools(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": 'Thought: need more data.\nAction: search_spend["HP toner suppliers"]',
                "tool_calls": None,
            }
        return {"content": 'Thought: now I know.\nFinal Answer: HP is the main toner supplier.', "tool_calls": None}

    monkeypatch.setattr(chat_react, "chat_with_tools", fake_chat_with_tools)

    steps = list(chat_react.answer_with_react_stream(message="Who supplies our toner?", context=[]))

    assert len(steps) == 2
    action_step, action_final = steps[0]
    assert action_step.tool == "search_spend"
    assert action_final is None
    _, final_answer = steps[1]
    assert final_answer is not None
    assert "HP" in final_answer


def test_stream_guard_yields_a_single_synthetic_step_with_the_guard_message(monkeypatch):
    monkeypatch.setattr(chat_react, "chat", lambda messages: "should not be called")

    steps = list(chat_react.answer_with_react_stream(message="what is my password?", context=[]))

    assert len(steps) == 1
    step_obj, final_answer = steps[0]
    assert step_obj.tool is None
    assert final_answer is not None
    assert "cannot be processed" in final_answer


# --- top_expenses: real ranking tool, not semantic search ---------------


def test_top_expenses_tool_ranks_by_total_descending(db):
    """search_spend can only surface items textually similar to the query,
    so "what was our highest expense" needs a real ORDER BY total DESC
    query instead - this is what led the chat to confidently name the wrong
    (or an unverified) top expense before this tool existed."""
    owner = _make_user(db, "topexpenses@test.com")
    _make_item(db, owner, "Toner", "Office Depot", 150.0)
    _make_item(db, owner, "Due diligence", "Deloitte Consulting", 12000.0)
    _make_item(db, owner, "Laptop", "Dell", 2000.0)

    result = top_expenses_tool_for(owner.id, db).fn("2")

    lines = result.splitlines()
    assert len(lines) == 2
    assert "Deloitte Consulting" in lines[0] and "€12,000.00" in lines[0]
    assert "Dell" in lines[1]


def test_build_react_call_only_adds_top_expenses_tool_when_db_and_user_id_given(db):
    without_db = chat_react._build_react_call("q", [], None, None, None, "en")
    assert [t.name for t in without_db["tools"]] == ["search_spend"]

    with_db = chat_react._build_react_call("q", [], None, None, None, "en", db, 1)
    assert [t.name for t in with_db["tools"]] == ["search_spend", "top_expenses"]


def test_react_loop_can_call_top_expenses_via_structured_tool_call(db, monkeypatch):
    owner = _make_user(db, "toprct@test.com")
    _make_item(db, owner, "Due diligence", "Deloitte Consulting", 12000.0)
    _make_item(db, owner, "Toner", "Office Depot", 150.0)

    calls = {"n": 0}

    def fake_chat_with_tools(messages, tools):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": None,
                "tool_calls": [{"function": {"name": "top_expenses", "arguments": '{"input": "1"}'}}],
            }
        return {"content": "Thought: found it.\nFinal Answer: Deloitte Consulting, €12,000.00.", "tool_calls": None}

    monkeypatch.setattr(chat_react, "chat_with_tools", fake_chat_with_tools)

    reply = chat_react.answer_with_react(
        message="What was our highest expense?", context=[], db=db, user_id=owner.id,
    )

    assert calls["n"] == 2
    assert "Deloitte" in reply
