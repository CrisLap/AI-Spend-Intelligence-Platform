from __future__ import annotations

from app.core.config import settings
from app.services import ai


def test_chat_with_tools_prefers_ollama_plain_text(monkeypatch):
    """Ollama is tried first and, if it answers, its plain text is returned
    with no tool_calls - small local models aren't asked for structured
    calls at all (see chat_with_tools()'s docstring for why)."""
    monkeypatch.setattr(ai, "_ollama_chat", lambda messages: "Thought: ok.\nFinal Answer: done.")

    called_groq = {"n": 0}
    monkeypatch.setattr(ai, "_groq_chat_with_tools", lambda messages, tools: called_groq.update(n=1) or None)

    result = ai.chat_with_tools([{"role": "user", "content": "hi"}], tools=[])

    assert result == {"content": "Thought: ok.\nFinal Answer: done.", "tool_calls": None}
    assert called_groq["n"] == 0


def test_chat_with_tools_falls_back_to_groq_structured_calls_when_ollama_unreachable(monkeypatch):
    monkeypatch.setattr(ai, "_ollama_chat", lambda messages: None)
    fake_response = {
        "content": None,
        "tool_calls": [{"function": {"name": "search_spend", "arguments": '{"input": "toner"}'}}],
    }
    monkeypatch.setattr(ai, "_groq_chat_with_tools", lambda messages, tools: fake_response)

    result = ai.chat_with_tools([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])

    assert result == fake_response


def test_chat_with_tools_falls_back_to_offline_when_both_providers_unreachable(monkeypatch):
    monkeypatch.setattr(ai, "_ollama_chat", lambda messages: None)
    monkeypatch.setattr(ai, "_groq_chat_with_tools", lambda messages, tools: None)

    result = ai.chat_with_tools([{"role": "user", "content": "hi"}], tools=[])

    assert result["tool_calls"] is None
    assert "[Offline]" in result["content"]


def test_groq_chat_with_tools_returns_none_without_an_api_key(monkeypatch):
    monkeypatch.setattr(settings, "groq_api_key", None)
    assert ai._groq_chat_with_tools([{"role": "user", "content": "hi"}], tools=[]) is None
