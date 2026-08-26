from __future__ import annotations

import json
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.services.agents.react_engine import (
    ReactStep,
    ReactTrace,
    build_system_prompt,
    iter_react_steps,
    run_react,
    step_to_dict,
)
from app.services.agents.tools import build_contract_risk_tools, build_forecast_tools, build_tools
from app.services.ai import chat, chat_with_tools
from app.services.analytics import forecast_next_month_spend, get_supplier_variance
from app.services.contract_intelligence import search_contracts
from app.services.guardrails import sanitize_output, validate_input
from app.services.i18n_strings import translate as _t

_MAX_STEPS = 4

# Three agents share this one module/table/endpoint/frontend page (see
# AgentRun.agent_type) instead of each getting its own REST/UI - only the
# tool registry, system prompt and recommendation logic differ per type.
AGENT_TYPES = ("cost_saving", "forecast", "contract_risk")
DEFAULT_AGENT_TYPE = "cost_saving"

_ROLE_DESCRIPTIONS = {
    "cost_saving": (
        "You are the AI Cost Saving Agent for a corporate spend intelligence "
        "platform. Given a goal, investigate the company's real spend data step "
        "by step - checking spend overview, supplier variance, anomalies and "
        "contract terms as needed - before concluding. For any question about "
        "the highest/biggest/most expensive spend, use the top_expenses tool - "
        "it is a real ranking over every record, not a summary. Only state "
        "figures you actually retrieved via a tool; never invent numbers."
    ),
    "forecast": (
        "You are the AI Forecast Agent for a corporate spend intelligence "
        "platform. Given a goal, use the forecast_spend tool (and, if useful, "
        "spend_overview) to project next month's total spend from real monthly "
        "history, and explain the trend. For any question about the "
        "highest/biggest/most expensive spend, use the top_expenses tool "
        "instead - it is a real ranking over every record. Only state figures "
        "you actually retrieved via a tool; never invent numbers."
    ),
    "contract_risk": (
        "You are the AI Contract Risk Agent for a corporate spend intelligence "
        "platform. Given a goal, use contract_search to find risky clauses in "
        "indexed contracts - penalties, exclusivity, missing price caps, "
        "unfavorable termination terms - and summarize what was actually found. "
        "For any question about the highest/biggest/most expensive spend, use "
        "the top_expenses tool instead - it is a real ranking over every "
        "record. Only state what a tool actually returned; never invent "
        "clauses or numbers."
    ),
}

_TOOL_BUILDERS = {
    "cost_saving": build_tools,
    "forecast": build_forecast_tools,
    "contract_risk": build_contract_risk_tools,
}

# Heuristic assumption, not a measured fact: renegotiating a contract whose
# spend has increased significantly typically recovers a fraction of that
# increase, not all of it. Kept as a single named constant so it's easy to
# find, question, and adjust - the point is that every recommendation's
# "estimated saving" is a transparent formula over a real number
# (recent_total), not a fabricated absolute figure.
_ASSUMED_RENEGOTIATION_RECOVERY_RATE = 0.15
_VARIANCE_THRESHOLD_PCT = 20.0
_RENEWAL_SEARCH_QUERIES = (
    "rinnovo automatico tacito",
    "automatic renewal clause",
    "penale recesso anticipato",
)
_RENEWAL_SCORE_THRESHOLD = 0.55

_RISK_SEARCH_QUERIES = (
    "penale recesso anticipato",
    "clausola di esclusiva fornitore unico",
    "nessun tetto massimo aumento prezzi",
)
_RISK_SCORE_THRESHOLD = 0.55

# Recommendation text is deterministic (computed from real data, not LLM
# prose - see analyze()'s docstring), so it can be authored per-language up
# front rather than translated at request time. Rendered once when the run
# is created (_persist_run) using whichever lang the request carried, then
# stored fixed in AgentRun.recommendations_json - same "generated once,
# fixed thereafter" pattern as the rest of that row (summary, steps).
_STRINGS = {
    "en": {
        "uncategorized": "uncategorized category",
        "renegotiate_title": "Renegotiate the contract with {supplier}",
        "renegotiate_reason": "Spend up {pct:.1f}% (from €{prev:,.2f} to €{recent:,.2f}) in {categories}.",
        "renegotiate_evidence": (
            "Spend history: €{prev:,.2f} -> €{recent:,.2f} "
            "({prev_count} invoice lines in the previous period, {recent_count} in the recent period)."
        ),
        "renewal_title": "Review the renewal terms of contract '{source}'",
        "renewal_reason": (
            "The contract text contains an automatic renewal or penalty clause "
            "worth reviewing before it expires."
        ),
        "forecast_title": "Next month's spend forecast",
        "forecast_reason": (
            "Trend {trend_word} of €{trend:,.2f}/month calculated over {months} months "
            "of history. Forecast spend: €{forecast:,.2f}."
        ),
        "forecast_evidence": "Monthly history: {history}",
        "trend_up": "increasing",
        "trend_down": "decreasing",
        "trend_stable": "stable",
        "risk_title": "Contract risk detected in '{source}'",
        "risk_reason": 'The text semantically matches "{query}" - review the clause before renewal.',
    },
    "it": {
        "uncategorized": "categoria non classificata",
        "renegotiate_title": "Rinegozia il contratto con {supplier}",
        "renegotiate_reason": "Spesa in aumento del {pct:.1f}% (da €{prev:,.2f} a €{recent:,.2f}) su {categories}.",
        "renegotiate_evidence": (
            "Storico spesa: €{prev:,.2f} -> €{recent:,.2f} "
            "({prev_count} righe fattura nel periodo precedente, {recent_count} nel periodo recente)."
        ),
        "renewal_title": "Verifica le condizioni di rinnovo del contratto '{source}'",
        "renewal_reason": (
            "Il testo del contratto contiene una clausola di rinnovo automatico o penale "
            "che merita revisione prima della scadenza."
        ),
        "forecast_title": "Previsione di spesa per il prossimo mese",
        "forecast_reason": (
            "Trend {trend_word} di €{trend:,.2f}/mese calcolato su {months} mesi di storico. "
            "Spesa prevista: €{forecast:,.2f}."
        ),
        "forecast_evidence": "Storico mensile: {history}",
        "trend_up": "in aumento",
        "trend_down": "in calo",
        "trend_stable": "stabile",
        "risk_title": "Rischio contrattuale rilevato in '{source}'",
        "risk_reason": 'Il testo corrisponde semanticamente a "{query}" - verificare la clausola prima del rinnovo.',
    },
}


def _variance_recommendations(user_id: int | list[int] | None, db: Session, lang: str = "en") -> list[dict]:
    """Flags suppliers whose recent-period spend rose by more than
    _VARIANCE_THRESHOLD_PCT vs. the previous period (see
    analytics.get_supplier_variance) as renegotiation candidates.

    user_id here is the caller's visible role-scope (a list of ids, or None
    for admin - see core/deps.py::get_visible_user_ids), not necessarily a
    single user, since the underlying spend data is now shared per role."""
    recs = []
    for v in get_supplier_variance(user_id=user_id, db=db):
        if v["variance_pct"] < _VARIANCE_THRESHOLD_PCT:
            continue
        categories = ", ".join(v["categories"]) or _t(_STRINGS, lang, "uncategorized")
        recs.append({
            "title": _t(_STRINGS, lang, "renegotiate_title", supplier=v["supplier"]),
            "reason": _t(
                _STRINGS, lang, "renegotiate_reason",
                pct=v["variance_pct"], prev=v["previous_total"], recent=v["recent_total"], categories=categories,
            ),
            "supplier": v["supplier"],
            "category": v["categories"][0] if v["categories"] else None,
            "estimated_saving": round(v["recent_total"] * _ASSUMED_RENEGOTIATION_RECOVERY_RATE, 2),
            "currency": "EUR",
            "confidence": "medium",
            "evidence": [
                _t(
                    _STRINGS, lang, "renegotiate_evidence",
                    prev=v["previous_total"], recent=v["recent_total"],
                    prev_count=v["previous_count"], recent_count=v["recent_count"],
                )
            ],
        })
    return recs


def _contract_recommendations(user_id: int | list[int] | None, db: Session, lang: str = "en") -> list[dict]:
    """Flags contracts whose indexed text semantically matches renewal/penalty
    language, using the real contract-clause RAG (contract_intelligence.py) -
    not a keyword scan of the raw file."""
    recs = []
    seen_docs: set[int] = set()
    for query in _RENEWAL_SEARCH_QUERIES:
        for hit in search_contracts(query, top_k=5, user_id=user_id, db=db):
            doc_id = hit.get("document_id")
            if doc_id is None or doc_id in seen_docs or hit["score"] < _RENEWAL_SCORE_THRESHOLD:
                continue
            seen_docs.add(doc_id)
            recs.append({
                "title": _t(_STRINGS, lang, "renewal_title", source=hit.get("source") or doc_id),
                "reason": _t(_STRINGS, lang, "renewal_reason"),
                "supplier": None,
                "category": None,
                "estimated_saving": None,
                "currency": "EUR",
                "confidence": "low",
                "evidence": [sanitize_output((hit.get("text") or "")[:300])],
            })
    return recs


def _forecast_recommendations(user_id: int | list[int] | None, db: Session, lang: str = "en") -> list[dict]:
    """Turns the linear-trend forecast (analytics.forecast_next_month_spend)
    into the same recommendation shape the other agents produce, so the
    frontend needs no special case - but with no estimated_saving, since a
    forecast isn't a saving opportunity and inventing one here would violate
    the "no fabricated numbers" rule this whole module is built around."""
    result = forecast_next_month_spend(user_id=user_id, db=db)
    if not result["available"]:
        return []
    trend = result["trend_per_month"]
    trend_key = "trend_up" if trend > 0 else "trend_down" if trend < 0 else "trend_stable"
    trend_word = _t(_STRINGS, lang, trend_key)
    history = ", ".join(f"{m}: €{t:,.2f}" for m, t in zip(result["months"], result["monthly_totals"]))
    return [{
        "title": _t(_STRINGS, lang, "forecast_title"),
        "reason": _t(
            _STRINGS, lang, "forecast_reason",
            trend_word=trend_word, trend=abs(trend), months=len(result["months"]), forecast=result["forecast_next_month"],
        ),
        "supplier": None,
        "category": None,
        "estimated_saving": None,
        "currency": "EUR",
        "confidence": "medium" if len(result["months"]) >= 5 else "low",
        "evidence": [_t(_STRINGS, lang, "forecast_evidence", history=history)],
        "chart": {
            "months": result["months"],
            "monthly_totals": result["monthly_totals"],
            "forecast_next_month": result["forecast_next_month"],
        },
    }]


def _contract_risk_recommendations(user_id: int | list[int] | None, db: Session, lang: str = "en") -> list[dict]:
    """Same real contract-clause RAG as _contract_recommendations(), just
    searched for risk language (penalties, exclusivity, no price cap)
    instead of renewal language - the Contract Risk Agent's counterpart."""
    recs = []
    seen: set[tuple[int, str]] = set()
    for query in _RISK_SEARCH_QUERIES:
        for hit in search_contracts(query, top_k=5, user_id=user_id, db=db):
            doc_id = hit.get("document_id")
            key = (doc_id, query)
            if doc_id is None or key in seen or hit["score"] < _RISK_SCORE_THRESHOLD:
                continue
            seen.add(key)
            recs.append({
                "title": _t(_STRINGS, lang, "risk_title", source=hit.get("source") or doc_id),
                "reason": _t(_STRINGS, lang, "risk_reason", query=query),
                "supplier": None,
                "category": None,
                "estimated_saving": None,
                "currency": "EUR",
                "confidence": "low",
                "evidence": [sanitize_output((hit.get("text") or "")[:300])],
            })
    return recs


def _compute_recommendations(
    agent_type: str, visible_user_ids: int | list[int] | None, db: Session, lang: str = "en"
) -> list[dict]:
    if agent_type == "forecast":
        return _forecast_recommendations(visible_user_ids, db, lang)
    if agent_type == "contract_risk":
        return _contract_risk_recommendations(visible_user_ids, db, lang)
    recommendations = _variance_recommendations(visible_user_ids, db, lang) + _contract_recommendations(
        visible_user_ids, db, lang
    )
    recommendations.sort(key=lambda r: r.get("estimated_saving") or 0, reverse=True)
    return recommendations


def _react_kwargs(
    goal: str, visible_user_ids: int | list[int] | None, db: Session, agent_type: str, lang: str = "en"
) -> dict:
    """Shared setup between analyze() (batch) and analyze_stream() (SSE) -
    both run the identical ReAct configuration, just consumed differently."""
    tools = _TOOL_BUILDERS[agent_type](visible_user_ids, db)
    return {
        "chat_fn": chat,
        "system_prompt": build_system_prompt(_ROLE_DESCRIPTIONS[agent_type], tools, lang=lang),
        "task_prompt": f"## Goal\n{goal}",
        "tools": tools,
        "initial_observations": None,
        "max_steps": _MAX_STEPS,
        # Prefer native structured tool calls (Groq's `tools=`) over
        # text-parsed Thought/Action/Observation - see react_engine.py's
        # docstring for why both mechanisms exist (also used by chat_react.py).
        "chat_with_tools_fn": chat_with_tools,
    }


def _persist_run(
    goal: str,
    user_id: int,
    visible_user_ids: int | list[int] | None,
    agent_type: str,
    trace: ReactTrace,
    db: Session,
    lang: str = "en",
) -> AgentRun:
    """Computes the deterministic recommendations and saves the run - shared
    tail end of both analyze() and analyze_stream(), see analyze()'s
    docstring for why the recommendations are computed independently of the
    ReAct trace rather than parsed out of it.

    user_id (a single id) owns the persisted AgentRun - run history stays
    private per user even though the underlying spend data it's computed
    over (visible_user_ids) is now shared per role."""
    recommendations = _compute_recommendations(agent_type, visible_user_ids, db, lang)

    run = AgentRun(
        user_id=user_id,
        agent_type=agent_type,
        goal=goal,
        steps_json=json.dumps([step_to_dict(s) for s in trace.steps], ensure_ascii=False),
        recommendations_json=json.dumps(recommendations, ensure_ascii=False),
        summary=trace.final_answer,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


_UNSCOPED = object()  # sentinel: distinguishes "caller omitted visible_user_ids" (default to just [user_id]) from an explicit None (admin - no filter)


def analyze(
    goal: str,
    user_id: int,
    db: Session,
    agent_type: str = DEFAULT_AGENT_TYPE,
    lang: str = "en",
    visible_user_ids: int | list[int] | None = _UNSCOPED,  # type: ignore[assignment]
) -> AgentRun:
    """Runs one of the three agents (agent_type: "cost_saving", "forecast" or
    "contract_risk") for a goal and persists the result.

    user_id owns the persisted AgentRun (run history stays private per
    user). visible_user_ids is the caller's visible role-scope used to
    query the underlying spend data (see core/deps.py::get_visible_user_ids)
    - defaults to just [user_id] if not given, for callers/tests that don't
    need role-based sharing.

    Two things happen, deliberately decoupled:
      1. A real multi-step ReAct loop (run_react) where the LLM decides
         which tools to call and produces a narrative summary - this is
         what the frontend timeline shows as the agent "thinking".
      2. A deterministic Recommendation Engine that computes structured
         recommendations directly from the same underlying data functions,
         independent of which tools the LLM happened to call in its trace.
         This guarantees every recommendation's numbers are grounded in a
         real, reproducible calculation regardless of how the free-text
         ReAct conversation went - parsing structured figures back out of
         LLM prose would be far less reliable.

    See analyze_stream() for the incremental (SSE) equivalent of this same
    pipeline.

    Recommendations are computed unconditionally even when the guard below
    blocks the goal (skipping the LLM call): they're derived from real spend
    data via agent_type alone (see _compute_recommendations), never from the
    goal text, so they stay valid whether or not the ReAct trace ran.
    """
    if visible_user_ids is _UNSCOPED:
        visible_user_ids = user_id
    guard = validate_input(goal, lang=lang)
    if guard:
        trace = ReactTrace(final_answer=guard)
    else:
        trace = run_react(**_react_kwargs(goal, visible_user_ids, db, agent_type, lang))
        trace.final_answer = sanitize_output(trace.final_answer)
    return _persist_run(goal, user_id, visible_user_ids, agent_type, trace, db, lang)


def analyze_stream(
    goal: str,
    user_id: int,
    db: Session,
    agent_type: str = DEFAULT_AGENT_TYPE,
    lang: str = "en",
    visible_user_ids: int | list[int] | None = _UNSCOPED,  # type: ignore[assignment]
) -> Iterator[str]:
    """Same pipeline as analyze(), but yields each ReAct step as a
    server-sent event as soon as it's produced, instead of waiting for the
    whole trace before responding. Ends with a `done` event carrying the
    persisted run (id, summary, recommendations) - the same shape the
    non-streaming endpoint returns - so the frontend can render the
    recommendation cards once the stream closes.

    Yields raw `text/event-stream` chunks (each already terminated by the
    blank line the SSE format requires), ready to hand to
    fastapi.responses.StreamingResponse.
    """
    if visible_user_ids is _UNSCOPED:
        visible_user_ids = user_id
    guard = validate_input(goal, lang=lang)
    if guard:
        trace = ReactTrace(final_answer=guard)
        step_obj = ReactStep(index=0, thought=None, tool=None, tool_input=None, observation=None, mode=None)
        yield f"event: step\ndata: {json.dumps(step_to_dict(step_obj), ensure_ascii=False)}\n\n"
    else:
        trace = ReactTrace()
        for step, final_answer in iter_react_steps(**_react_kwargs(goal, visible_user_ids, db, agent_type, lang)):
            trace.steps.append(step)
            yield f"event: step\ndata: {json.dumps(step_to_dict(step), ensure_ascii=False)}\n\n"
            if final_answer is not None:
                trace.final_answer = sanitize_output(final_answer)

    run = _persist_run(goal, user_id, visible_user_ids, agent_type, trace, db, lang)
    done_payload = {
        "id": run.id,
        "goal": run.goal,
        "agent_type": run.agent_type,
        "summary": run.summary,
        "recommendations": json.loads(run.recommendations_json or "[]"),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
