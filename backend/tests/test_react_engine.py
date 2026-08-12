from __future__ import annotations

from app.services.agents.react_engine import Tool, run_react


def test_single_tool_loop_calls_tool_then_answers():
    """Generic loop parity check: this is the exact scenario
    chat_react.py's ReAct loop already covered before the refactor - a tool
    call followed by a final answer - now driven through the shared engine
    with an explicit tool registry instead of a single hardcoded tool."""
    calls = {"n": 0}

    def fake_chat(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return 'Thought: need data.\nAction: search_spend["toner"]'
        return "Thought: done.\nFinal Answer: Found it."

    searched = {}

    def fake_search(query: str):
        searched["query"] = query
        return [{"text": "toner invoice", "score": 0.9}]

    tool = Tool(name="search_spend", description="search", fn=fake_search)

    trace = run_react(
        chat_fn=fake_chat,
        system_prompt="sys",
        task_prompt="task",
        tools=[tool],
        initial_observations="No relevant results found.",
        max_steps=3,
    )

    assert calls["n"] == 2
    assert searched["query"] == "toner"
    assert trace.final_answer == "Found it."
    assert len(trace.steps) == 2
    assert trace.steps[0].tool == "search_spend"
    assert trace.steps[0].observation is not None
    assert trace.steps[1].tool is None  # the Final Answer step


def test_multi_tool_loop_dispatches_to_the_named_tool():
    """More than one tool registered - the engine must route the Action to
    the tool the model actually named, not just the first one."""
    calls = {"n": 0}

    def fake_chat(messages):
        calls["n"] += 1
        if calls["n"] == 1:
            return 'Thought: check variance.\nAction: supplier_variance["all"]'
        return "Thought: done.\nFinal Answer: Microsoft spend rose."

    invoked = {}
    tool_a = Tool(name="spend_overview", description="a", fn=lambda q: invoked.setdefault("a", q) or "overview text")
    tool_b = Tool(name="supplier_variance", description="b", fn=lambda q: invoked.setdefault("b", q) or "variance text")

    trace = run_react(
        chat_fn=fake_chat,
        system_prompt="sys",
        task_prompt="task",
        tools=[tool_a, tool_b],
        max_steps=3,
    )

    assert "b" in invoked and invoked["b"] == "all"
    assert "a" not in invoked
    assert trace.final_answer == "Microsoft spend rose."


def test_unknown_tool_name_falls_back_to_parsed_thought():
    """The model naming a tool that isn't registered must not crash the
    loop - it should stop and surface the parsed `Thought:` text, not the
    raw reply (which would leak the unexecuted `Action: tool[...]` syntax
    to the end user)."""

    def fake_chat(messages):
        return 'Thought: x.\nAction: nonexistent_tool["y"]'

    tool = Tool(name="search_spend", description="search", fn=lambda q: [])

    trace = run_react(
        chat_fn=fake_chat,
        system_prompt="sys",
        task_prompt="task",
        tools=[tool],
        max_steps=2,
    )

    assert trace.final_answer == "x."
    assert "Action:" not in trace.final_answer


def test_max_steps_is_respected_even_without_a_final_answer():
    """If the model keeps calling a tool and never commits to a Final
    Answer, the loop must still terminate at max_steps, not run forever."""
    calls = {"n": 0}

    def fake_chat(messages):
        calls["n"] += 1
        return 'Thought: more.\nAction: search_spend["again"]'

    tool = Tool(name="search_spend", description="search", fn=lambda q: [{"text": "x", "score": 0.1}])

    trace = run_react(
        chat_fn=fake_chat,
        system_prompt="sys",
        task_prompt="task",
        tools=[tool],
        max_steps=3,
    )

    assert calls["n"] == 3
    assert trace.final_answer  # falls back to the last raw reply


def test_structured_mode_dispatches_a_native_tool_call():
    """When chat_with_tools_fn is provided, a tool_call in the response
    drives dispatch directly (no regex text-parsing needed) - this is the
    Groq-native path the Cost Saving Agent uses."""
    calls = {"n": 0}

    def fake_chat_with_tools(messages, tools):
        calls["n"] += 1
        assert tools and tools[0]["function"]["name"] == "search_spend"
        if calls["n"] == 1:
            return {
                "content": None,
                "tool_calls": [{"function": {"name": "search_spend", "arguments": '{"input": "toner"}'}}],
            }
        return {"content": "Thought: done.\nFinal Answer: Found it via structured call.", "tool_calls": None}

    searched = {}
    tool = Tool(name="search_spend", description="search", fn=lambda q: searched.setdefault("query", q) or [])

    trace = run_react(
        chat_fn=lambda messages: "unused",
        system_prompt="sys",
        task_prompt="task",
        tools=[tool],
        max_steps=3,
        chat_with_tools_fn=fake_chat_with_tools,
    )

    assert calls["n"] == 2
    assert searched["query"] == "toner"
    assert trace.final_answer == "Found it via structured call."
    assert trace.steps[0].mode == "structured"


def test_structured_mode_falls_back_to_text_parsing_without_a_tool_call():
    """If chat_with_tools_fn returns plain content (no tool_calls) - e.g.
    Ollama answered, which chat_with_tools() never asks for structured
    calls - the turn still parses via the text ReAct format instead of
    being discarded."""

    def fake_chat_with_tools(messages, tools):
        return {"content": "Thought: ok.\nFinal Answer: Plain text answer.", "tool_calls": None}

    tool = Tool(name="search_spend", description="search", fn=lambda q: [])

    trace = run_react(
        chat_fn=lambda messages: "unused",
        system_prompt="sys",
        task_prompt="task",
        tools=[tool],
        max_steps=2,
        chat_with_tools_fn=fake_chat_with_tools,
    )

    assert trace.final_answer == "Plain text answer."


def test_structured_mode_ignores_a_tool_call_for_an_unregistered_tool():
    def fake_chat_with_tools(messages, tools):
        return {
            "content": None,
            "tool_calls": [{"function": {"name": "not_registered", "arguments": "{}"}}],
        }

    tool = Tool(name="search_spend", description="search", fn=lambda q: [])

    trace = run_react(
        chat_fn=lambda messages: "unused",
        system_prompt="sys",
        task_prompt="task",
        tools=[tool],
        max_steps=2,
        chat_with_tools_fn=fake_chat_with_tools,
    )

    # No content and no matching tool -> same "give up gracefully" fallback
    # as the text-parsed unknown-tool/no-format case.
    assert trace.final_answer == "I couldn't find enough information to answer that."
