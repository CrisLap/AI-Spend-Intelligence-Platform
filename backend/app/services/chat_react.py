from __future__ import annotations

import re
from collections.abc import Callable

from app.services.ai import chat
from app.services.guardrails import sanitize_output, validate_input

_MAX_REACT_STEPS = 3

_REACT_SYSTEM_PROMPT = (
    "You are the AI Spend Intelligence assistant. You answer questions about "
    "company spend data using a ReAct loop (Thought / Action / Observation).\n\n"
    "You have one tool available:\n"
    "  search_spend[\"<query>\"] - semantic search over invoices/orders/contracts, "
    "returns the most relevant spend line items.\n\n"
    "On every turn, respond with EXACTLY one of these two formats and nothing else:\n\n"
    "Thought: <your reasoning about what to do next>\n"
    "Action: search_spend[\"<a focused search query>\"]\n\n"
    "  -- or, once you have enough information --\n\n"
    "Thought: <your reasoning>\n"
    "Final Answer: <the answer to the user's question, with citations to the "
    "document name and supplier for every figure you mention>\n\n"
    "Only give a Final Answer when the observations gathered so far actually "
    "support it. If nothing relevant was found after searching, say so plainly "
    "in the Final Answer instead of guessing.\n"
)


def _format_observations(context: list[dict]) -> str:
    if not context:
        return "No relevant documents found."
    return "\n".join(
        f"[{i + 1}] {c['text']} (score: {c['score']})" for i, c in enumerate(context)
    )


def _parse_step(reply: str) -> tuple[str | None, str | None]:
    """Returns (action_query, final_answer). Exactly one is non-None, unless
    the model didn't follow the format at all, in which case both are None
    and the caller should treat the raw reply as the final answer."""
    final_match = re.search(r"Final Answer:\s*(.+)", reply, re.DOTALL)
    if final_match:
        return None, final_match.group(1).strip()
    action_match = re.search(r'Action:\s*search_spend\[\s*"(.+?)"\s*\]', reply, re.DOTALL)
    if action_match:
        return action_match.group(1).strip(), None
    return None, None


def answer_with_react(
    message: str,
    context: list[dict],
    conversation_history: list[dict] | None = None,
    retrieve_fn: Callable[[str], list[dict]] | None = None,
    history_summary: str | None = None,
) -> str:
    """Runs a genuine ReAct loop: the model can issue further search_spend
    actions (via retrieve_fn) before committing to a Final Answer, instead of
    reasoning over a single fixed context in one shot."""
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

    scratchpad_steps: list[str] = [
        f"Observation 0 (initial search): {_format_observations(context)}"
    ]
    last_reply = ""

    for step in range(_MAX_REACT_STEPS):
        prompt = (
            f"## Conversation History\n{history_text or 'None yet.'}\n\n"
            f"## Question\n{message}\n\n"
            f"## Scratchpad\n" + "\n".join(scratchpad_steps) + "\n"
        )
        reply = chat([
            {"role": "system", "content": _REACT_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ])
        last_reply = reply or ""

        action_query, final_answer = _parse_step(last_reply)

        if final_answer:
            return sanitize_output(final_answer)

        if action_query and retrieve_fn is not None and step < _MAX_REACT_STEPS - 1:
            new_context = retrieve_fn(action_query)
            scratchpad_steps.append(f"Thought/Action (step {step + 1}): searched for \"{action_query}\"")
            scratchpad_steps.append(
                f"Observation {step + 1}: {_format_observations(new_context)}"
            )
            continue

        # Model didn't follow the Thought/Action/Final Answer format (common
        # with smaller local models), or we're out of steps: fall back to
        # treating the raw reply as the answer rather than looping forever.
        break

    return sanitize_output(last_reply or "I couldn't find enough information to answer that.")

