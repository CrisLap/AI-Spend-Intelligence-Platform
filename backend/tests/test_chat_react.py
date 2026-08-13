from __future__ import annotations

from app.services import chat_react


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
