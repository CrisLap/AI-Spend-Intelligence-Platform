from __future__ import annotations

from collections.abc import Callable, Iterator

from app.services.agents.react_engine import (
    ReactStep,
    Tool,
    build_system_prompt,
    format_observations,
    iter_react_steps,
    run_react,
)
from app.services.ai import chat, chat_with_tools
from app.services.guardrails import sanitize_output, validate_input

_MAX_REACT_STEPS = 3

_ROLE_DESCRIPTION = (
    "You are the AI Spend Intelligence assistant. You answer questions about "
    "company spend data using a ReAct loop (Thought / Action / Observation)."
)


def _build_react_call(
    message: str,
    context: list[dict],
    conversation_history: list[dict] | None,
    retrieve_fn: Callable[[str], list[dict]] | None,
    history_summary: str | None,
    lang: str,
) -> dict:
    """Shared setup between answer_with_react() (batch) and
    answer_with_react_stream() (SSE) - both run the identical ReAct
    configuration, just consumed differently. Mirrors
    cost_saving_agent.py::_react_kwargs's role for that agent family."""
    history_text = ""
    if history_summary:
        history_text += f"[Summary of earlier conversation]: {history_summary}\n"
    if conversation_history:
        history_text += "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:300]}"
            for m in conversation_history[-6:]
        )

    tool = Tool(
        name="search_spend",
        description=(
            "semantic search over invoices/orders/contracts, returns the "
            "most relevant spend line items."
        ),
        fn=lambda query: retrieve_fn(query) if retrieve_fn else [],
    )
    return {
        "chat_fn": chat,
        "system_prompt": build_system_prompt(_ROLE_DESCRIPTION, [tool], lang=lang),
        "task_prompt": f"## Conversation History\n{history_text or 'None yet.'}\n\n## Question\n{message}",
        "tools": [tool],
        "initial_observations": format_observations(context),
        "max_steps": _MAX_REACT_STEPS,
        # Prefer native structured tool calls (Groq's `tools=`) over
        # text-parsed Thought/Action/Observation, same as cost_saving_agent.py.
        # Required for agentic Groq models (e.g. openai/gpt-oss-20b): they
        # attempt a real structured tool call for "search_spend" whenever the
        # system prompt describes it as an available tool, regardless of the
        # plain-text Thought/Action instructions - if no `tools=` schema is
        # sent with the request, Groq rejects that response with a 400
        # "tool_use_failed" error ("Tool choice is none, but model called a
        # tool") instead of returning it as text, which used to make every
        # Groq reply fail straight through to the offline fallback.
        "chat_with_tools_fn": chat_with_tools,
    }


def answer_with_react(
    message: str,
    context: list[dict],
    conversation_history: list[dict] | None = None,
    retrieve_fn: Callable[[str], list[dict]] | None = None,
    history_summary: str | None = None,
    lang: str = "en",
) -> str:
    """Runs a genuine ReAct loop: the model can issue further search_spend
    actions (via retrieve_fn) before committing to a Final Answer, instead of
    reasoning over a single fixed context in one shot.

    Thin wrapper around the generic multi-tool engine in
    app.services.agents.react_engine (also used by the Cost Saving Agent) -
    kept as its own function because chat_service.py depends on this exact
    signature and chat_service tests monkeypatch this module's `chat`.
    """
    guard = validate_input(message, lang=lang)
    if guard:
        return guard

    trace = run_react(**_build_react_call(message, context, conversation_history, retrieve_fn, history_summary, lang))
    return sanitize_output(trace.final_answer)


def answer_with_react_stream(
    message: str,
    context: list[dict],
    conversation_history: list[dict] | None = None,
    retrieve_fn: Callable[[str], list[dict]] | None = None,
    history_summary: str | None = None,
    lang: str = "en",
) -> Iterator[tuple[ReactStep, str | None]]:
    """Same pipeline as answer_with_react(), but yields each ReAct step as it
    happens instead of returning only the final answer - the chat
    equivalent of cost_saving_agent.py::analyze_stream. A guarded message
    short-circuits into a single synthetic step carrying the guard message
    as its final answer, so callers never need a separate non-streaming
    guard path."""
    guard = validate_input(message, lang=lang)
    if guard:
        yield ReactStep(index=0, thought=None, tool=None, tool_input=None, observation=None, mode=None), guard
        return

    for step_obj, final_answer in iter_react_steps(
        **_build_react_call(message, context, conversation_history, retrieve_fn, history_summary, lang)
    ):
        if final_answer is not None:
            final_answer = sanitize_output(final_answer)
        yield step_obj, final_answer
