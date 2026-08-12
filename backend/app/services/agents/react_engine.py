from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field


@dataclass
class Tool:
    """A single named tool an agent can call. `fn` takes the model's raw
    tool-input string and returns either a list of {text, score, ...}
    observation dicts (rendered as a numbered, scored list) or a plain
    string (used as-is) - the same shape chat_react.py's search_spend
    already produces, generalized so any number of tools can share one
    ReAct loop."""

    name: str
    description: str
    fn: Callable[[str], list[dict] | str]


@dataclass
class ReactStep:
    index: int
    thought: str | None
    tool: str | None
    tool_input: str | None
    observation: str | None
    # "structured" when the tool call came from the provider's native
    # function-calling (Groq's `tools=`), "text_parsed" when it was
    # regex-parsed out of a Thought/Action/Observation reply. None for a
    # Final Answer step, or when the engine wasn't run in structured mode
    # at all. Surfaced mainly so the trace can show which mechanism
    # actually produced a given step - useful for a technical reader, not
    # required for the agent to function.
    mode: str | None = None


@dataclass
class ReactTrace:
    steps: list[ReactStep] = field(default_factory=list)
    final_answer: str = ""


def format_observations(context: list[dict] | str) -> str:
    if isinstance(context, str):
        return context or "No relevant results found."
    if not context:
        return "No relevant results found."
    return "\n".join(
        f"[{i + 1}] {c.get('text', c)} (score: {c.get('score', '?')})" for i, c in enumerate(context)
    )


def build_system_prompt(role_description: str, tools: list[Tool]) -> str:
    tool_lines = "\n".join(f'  {t.name}["<input>"] - {t.description}' for t in tools)
    return (
        f"{role_description}\n\n"
        f"You have the following tool(s) available:\n{tool_lines}\n\n"
        "On every turn, respond with EXACTLY one of these two formats and nothing else:\n\n"
        "Thought: <your reasoning about what to do next>\n"
        f'Action: {tools[0].name}["<a focused input for that tool>"]\n\n'
        "  -- or, once you have enough information --\n\n"
        "Thought: <your reasoning>\n"
        "Final Answer: <your answer, citing the evidence gathered>\n\n"
        "Only give a Final Answer when the observations gathered so far actually "
        "support it. If nothing relevant was found after searching, say so plainly "
        "instead of guessing.\n"
    )


def tool_to_openai_schema(tool: Tool) -> dict:
    """Every tool in this codebase takes one free-text `input` string (a
    search query, a supplier filter, or a placeholder like "overview") -
    so this maps uniformly to a single required string parameter rather
    than needing a bespoke JSON schema per tool."""
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": {"input": {"type": "string", "description": "The input to pass to this tool."}},
                "required": ["input"],
            },
        },
    }


_ACTION_RE = re.compile(r'Action:\s*(\w+)\[\s*"(.+?)"\s*\]', re.DOTALL)
_FINAL_RE = re.compile(r"Final Answer:\s*(.+)", re.DOTALL)
_THOUGHT_RE = re.compile(r"Thought:\s*(.+?)(?:\nAction:|\nFinal Answer:|$)", re.DOTALL)


def _parse_step(reply: str) -> tuple[str | None, str | None, str | None]:
    """Returns (tool_name, tool_input, final_answer). Exactly one of
    (tool_name+tool_input) or final_answer is set, unless the model didn't
    follow the format at all, in which case all three are None and the
    caller should treat the raw reply as the final answer."""
    final_match = _FINAL_RE.search(reply)
    if final_match:
        return None, None, final_match.group(1).strip()
    action_match = _ACTION_RE.search(reply)
    if action_match:
        return action_match.group(1).strip(), action_match.group(2).strip(), None
    return None, None, None


def _parse_structured_turn(
    result: dict, tool_map: dict[str, Tool]
) -> tuple[str | None, str | None, str | None, str | None, str]:
    """Interprets one turn of chat_with_tools()'s {"content", "tool_calls"}
    result. Returns (tool_name, tool_input, final_answer, thought, mode).

    Only the first tool_call is acted on when the provider returns more
    than one - this engine's scratchpad is built around one action per
    turn (matching the text-parsed ReAct format everywhere else), so
    executing several tools in parallel here would break that invariant
    for no real benefit at this codebase's scale.
    """
    tool_calls = result.get("tool_calls")
    content = result.get("content") or ""
    if tool_calls:
        call = tool_calls[0]
        name = call.get("function", {}).get("name")
        if name in tool_map:
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except (ValueError, TypeError):
                args = {}
            return name, str(args.get("input", "")), None, None, "structured"
    # No usable structured tool call this turn (Groq answered in plain text,
    # or fell through to Ollama/offline inside chat_with_tools): fall back to
    # the same text parsing every other path uses, so a reply without a
    # tool_call still degrades gracefully instead of being discarded.
    tool_name, tool_input, final_answer = _parse_step(content)
    thought_match = _THOUGHT_RE.search(content)
    thought = thought_match.group(1).strip() if thought_match else None
    if not tool_name and not final_answer:
        final_answer = content or None
    return tool_name, tool_input, final_answer, thought, "text_parsed"


def iter_react_steps(
    chat_fn: Callable[[list[dict]], str],
    system_prompt: str,
    task_prompt: str,
    tools: list[Tool],
    initial_observations: str | None = None,
    max_steps: int = 3,
    chat_with_tools_fn: Callable[[list[dict], list[dict]], dict] | None = None,
) -> Iterator[tuple[ReactStep, str | None]]:
    """The actual ReAct loop, as a generator - the single implementation
    both run_react() (batch, used everywhere the full trace is needed at
    once) and the SSE streaming endpoint (incremental, one step per
    server-sent event) consume. Yields (step, final_answer) tuples;
    final_answer is None for every step except the last one, whose
    presence signals loop termination - callers should stop iterating
    once they see a non-None final_answer, exactly like `return` would.

    See run_react()'s docstring for the tool registry / structured-mode
    behavior this implements; this function only changes *how* the result
    is delivered (incrementally vs. all at once), not the loop's logic.
    """
    tool_map = {t.name: t for t in tools}
    tool_schemas = [tool_to_openai_schema(t) for t in tools] if chat_with_tools_fn else None

    scratchpad_steps: list[str] = []
    if initial_observations is not None:
        scratchpad_steps.append(f"Observation 0 (initial context): {initial_observations}")

    last_reply = ""
    steps_yielded = 0
    for step in range(max_steps):
        prompt = (
            f"{task_prompt}\n\n"
            "## Scratchpad\n" + ("\n".join(scratchpad_steps) if scratchpad_steps else "(empty)") + "\n"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        if chat_with_tools_fn is not None:
            result = chat_with_tools_fn(messages, tool_schemas)
            tool_name, tool_input, final_answer, thought, mode = _parse_structured_turn(result, tool_map)
            last_reply = result.get("content") or ""
        else:
            reply = chat_fn(messages)
            last_reply = reply or ""
            tool_name, tool_input, final_answer = _parse_step(last_reply)
            thought_match = _THOUGHT_RE.search(last_reply)
            thought = thought_match.group(1).strip() if thought_match else None
            mode = "text_parsed"

        if final_answer:
            step_obj = ReactStep(index=step, thought=thought, tool=None, tool_input=None, observation=None, mode=None)
            yield step_obj, final_answer
            return

        if tool_name and tool_name in tool_map and step < max_steps - 1:
            tool = tool_map[tool_name]
            observation_text = format_observations(tool.fn(tool_input))
            scratchpad_steps.append(f'Thought/Action (step {step + 1}): called {tool_name}["{tool_input}"]')
            scratchpad_steps.append(f"Observation {step + 1}: {observation_text}")
            step_obj = ReactStep(
                index=step, thought=thought, tool=tool_name, tool_input=tool_input,
                observation=observation_text, mode=mode,
            )
            steps_yielded += 1
            yield step_obj, None
            continue

        # Model didn't follow the format, referenced an unknown tool, or
        # we're out of steps: stop rather than looping forever. Falls back
        # to the parsed `thought` (plain prose) instead of the raw reply,
        # since a reply that reached this point may still contain an
        # unexecuted "Action: tool[...]" line - showing that verbatim as
        # the "answer" would leak internal ReAct syntax to the end user.
        break

    final_answer = thought or last_reply or "I couldn't find enough information to answer that."
    step_obj = ReactStep(index=steps_yielded, thought=None, tool=None, tool_input=None, observation=None, mode=None)
    yield step_obj, final_answer


def run_react(
    chat_fn: Callable[[list[dict]], str],
    system_prompt: str,
    task_prompt: str,
    tools: list[Tool],
    initial_observations: str | None = None,
    max_steps: int = 3,
    chat_with_tools_fn: Callable[[list[dict], list[dict]], dict] | None = None,
) -> ReactTrace:
    """Runs a generic multi-tool ReAct loop (Thought/Action/Observation),
    capped at max_steps LLM turns, and returns the complete trace. Any
    number of named tools can be registered; the model picks which one to
    call (or commits straight to a Final Answer) at each step, driven
    entirely by system_prompt - this is the loop chat_react.py (1 tool)
    and the Cost Saving Agent (multiple tools) both run on top of.

    If chat_with_tools_fn is given (e.g. app.services.ai.chat_with_tools),
    each turn asks it for a native structured tool call first, falling back
    to text parsing only when the provider didn't return one - see
    _parse_structured_turn(). When omitted (the default), every turn is
    driven by plain-text Thought/Action/Observation parsing via chat_fn,
    unchanged from before this mode existed.

    This is a thin wrapper over iter_react_steps() that collects every
    yielded step into a ReactTrace - use iter_react_steps() directly (e.g.
    the SSE endpoint does) when steps need to reach a caller incrementally.
    """
    trace = ReactTrace()
    for step_obj, final_answer in iter_react_steps(
        chat_fn=chat_fn,
        system_prompt=system_prompt,
        task_prompt=task_prompt,
        tools=tools,
        initial_observations=initial_observations,
        max_steps=max_steps,
        chat_with_tools_fn=chat_with_tools_fn,
    ):
        trace.steps.append(step_obj)
        if final_answer is not None:
            trace.final_answer = final_answer
    return trace
