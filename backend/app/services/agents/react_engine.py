from __future__ import annotations

import re
from collections.abc import Callable
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


def run_react(
    chat_fn: Callable[[list[dict]], str],
    system_prompt: str,
    task_prompt: str,
    tools: list[Tool],
    initial_observations: str | None = None,
    max_steps: int = 3,
) -> ReactTrace:
    """Runs a generic multi-tool ReAct loop (Thought/Action/Observation),
    capped at max_steps LLM turns. Any number of named tools can be
    registered; the model picks which one to call (or commits straight to a
    Final Answer) at each step, driven entirely by system_prompt - this is
    the loop chat_react.py (1 tool) and the Cost Saving Agent (multiple
    tools) both run on top of."""
    tool_map = {t.name: t for t in tools}
    trace = ReactTrace()

    scratchpad_steps: list[str] = []
    if initial_observations is not None:
        scratchpad_steps.append(f"Observation 0 (initial context): {initial_observations}")

    last_reply = ""
    for step in range(max_steps):
        prompt = (
            f"{task_prompt}\n\n"
            "## Scratchpad\n" + ("\n".join(scratchpad_steps) if scratchpad_steps else "(empty)") + "\n"
        )
        reply = chat_fn([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ])
        last_reply = reply or ""

        tool_name, tool_input, final_answer = _parse_step(last_reply)
        thought_match = _THOUGHT_RE.search(last_reply)
        thought = thought_match.group(1).strip() if thought_match else None

        if final_answer:
            trace.final_answer = final_answer
            trace.steps.append(
                ReactStep(index=step, thought=thought, tool=None, tool_input=None, observation=None)
            )
            return trace

        if tool_name and tool_name in tool_map and step < max_steps - 1:
            tool = tool_map[tool_name]
            observation_text = format_observations(tool.fn(tool_input))
            scratchpad_steps.append(f'Thought/Action (step {step + 1}): called {tool_name}["{tool_input}"]')
            scratchpad_steps.append(f"Observation {step + 1}: {observation_text}")
            trace.steps.append(
                ReactStep(index=step, thought=thought, tool=tool_name, tool_input=tool_input, observation=observation_text)
            )
            continue

        # Model didn't follow the format, referenced an unknown tool, or
        # we're out of steps: stop and treat the raw reply as the answer
        # rather than looping forever.
        break

    trace.final_answer = last_reply or "I couldn't find enough information to answer that."
    trace.steps.append(
        ReactStep(index=len(trace.steps), thought=None, tool=None, tool_input=None, observation=None)
    )
    return trace
