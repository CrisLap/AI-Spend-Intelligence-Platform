from __future__ import annotations

from collections.abc import Callable

from app.services.agents.react_engine import Tool, build_system_prompt, format_observations, run_react
from app.services.ai import chat
from app.services.guardrails import sanitize_output, validate_input

_MAX_REACT_STEPS = 3

_ROLE_DESCRIPTION = (
    "You are the AI Spend Intelligence assistant. You answer questions about "
    "company spend data using a ReAct loop (Thought / Action / Observation)."
)


def answer_with_react(
    message: str,
    context: list[dict],
    conversation_history: list[dict] | None = None,
    retrieve_fn: Callable[[str], list[dict]] | None = None,
    history_summary: str | None = None,
) -> str:
    """Runs a genuine ReAct loop: the model can issue further search_spend
    actions (via retrieve_fn) before committing to a Final Answer, instead of
    reasoning over a single fixed context in one shot.

    Thin wrapper around the generic multi-tool engine in
    app.services.agents.react_engine (also used by the Cost Saving Agent) -
    kept as its own function because chat_service.py depends on this exact
    signature and chat_service tests monkeypatch this module's `chat`.
    """
    guard = validate_input(message)
    if guard:
        return guard

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
    system_prompt = build_system_prompt(_ROLE_DESCRIPTION, [tool])
    task_prompt = f"## Conversation History\n{history_text or 'None yet.'}\n\n## Question\n{message}"

    trace = run_react(
        chat_fn=chat,
        system_prompt=system_prompt,
        task_prompt=task_prompt,
        tools=[tool],
        initial_observations=format_observations(context),
        max_steps=_MAX_REACT_STEPS,
    )
    return sanitize_output(trace.final_answer)
