from __future__ import annotations

import json
from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.services.agents.react_engine import ReactStep, ReactTrace, build_system_prompt, iter_react_steps, run_react
from app.services.agents.tools import build_contract_risk_tools, build_forecast_tools, build_tools
from app.services.ai import chat, chat_with_tools
from app.services.analytics import forecast_next_month_spend, get_supplier_variance
from app.services.contract_intelligence import search_contracts

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
        "contract terms as needed - before concluding. Only state figures you "
        "actually retrieved via a tool; never invent numbers."
    ),
    "forecast": (
        "You are the AI Forecast Agent for a corporate spend intelligence "
        "platform. Given a goal, use the forecast_spend tool (and, if useful, "
        "spend_overview) to project next month's total spend from real monthly "
        "history, and explain the trend. Only state figures you actually "
        "retrieved via a tool; never invent numbers."
    ),
    "contract_risk": (
        "You are the AI Contract Risk Agent for a corporate spend intelligence "
        "platform. Given a goal, use contract_search to find risky clauses in "
        "indexed contracts - penalties, exclusivity, missing price caps, "
        "unfavorable termination terms - and summarize what was actually found. "
        "Only state what the tool actually returned; never invent clauses."
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


def _variance_recommendations(user_id: int, db: Session) -> list[dict]:
    """Flags suppliers whose recent-period spend rose by more than
    _VARIANCE_THRESHOLD_PCT vs. the previous period (see
    analytics.get_supplier_variance) as renegotiation candidates."""
    recs = []
    for v in get_supplier_variance(user_id=user_id, db=db):
        if v["variance_pct"] < _VARIANCE_THRESHOLD_PCT:
            continue
        recs.append({
            "title": f"Rinegozia il contratto con {v['supplier']}",
            "reason": (
                f"Spesa in aumento del {v['variance_pct']:.1f}% "
                f"(da €{v['previous_total']:,.2f} a €{v['recent_total']:,.2f}) "
                f"su {', '.join(v['categories']) or 'categoria non classificata'}."
            ),
            "supplier": v["supplier"],
            "category": v["categories"][0] if v["categories"] else None,
            "estimated_saving": round(v["recent_total"] * _ASSUMED_RENEGOTIATION_RECOVERY_RATE, 2),
            "currency": "EUR",
            "confidence": "medium",
            "evidence": [
                f"Storico spesa: €{v['previous_total']:,.2f} -> €{v['recent_total']:,.2f} "
                f"({v['previous_count']} righe fattura nel periodo precedente, "
                f"{v['recent_count']} nel periodo recente)."
            ],
        })
    return recs


def _contract_recommendations(user_id: int, db: Session) -> list[dict]:
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
                "title": f"Verifica le condizioni di rinnovo del contratto '{hit.get('source') or doc_id}'",
                "reason": "Il testo del contratto contiene una clausola di rinnovo automatico o penale che merita revisione prima della scadenza.",
                "supplier": None,
                "category": None,
                "estimated_saving": None,
                "currency": "EUR",
                "confidence": "low",
                "evidence": [(hit.get("text") or "")[:300]],
            })
    return recs


def _forecast_recommendations(user_id: int, db: Session) -> list[dict]:
    """Turns the linear-trend forecast (analytics.forecast_next_month_spend)
    into the same recommendation shape the other agents produce, so the
    frontend needs no special case - but with no estimated_saving, since a
    forecast isn't a saving opportunity and inventing one here would violate
    the "no fabricated numbers" rule this whole module is built around."""
    result = forecast_next_month_spend(user_id=user_id, db=db)
    if not result["available"]:
        return []
    trend = result["trend_per_month"]
    trend_word = "in aumento" if trend > 0 else "in calo" if trend < 0 else "stabile"
    history = ", ".join(f"{m}: €{t:,.2f}" for m, t in zip(result["months"], result["monthly_totals"]))
    return [{
        "title": "Previsione di spesa per il prossimo mese",
        "reason": (
            f"Trend {trend_word} di €{abs(trend):,.2f}/mese calcolato su {len(result['months'])} mesi "
            f"di storico. Spesa prevista: €{result['forecast_next_month']:,.2f}."
        ),
        "supplier": None,
        "category": None,
        "estimated_saving": None,
        "currency": "EUR",
        "confidence": "medium" if len(result["months"]) >= 5 else "low",
        "evidence": [f"Storico mensile: {history}"],
    }]


def _contract_risk_recommendations(user_id: int, db: Session) -> list[dict]:
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
                "title": f"Rischio contrattuale rilevato in '{hit.get('source') or doc_id}'",
                "reason": f'Il testo corrisponde semanticamente a "{query}" - verificare la clausola prima del rinnovo.',
                "supplier": None,
                "category": None,
                "estimated_saving": None,
                "currency": "EUR",
                "confidence": "low",
                "evidence": [(hit.get("text") or "")[:300]],
            })
    return recs


def _compute_recommendations(agent_type: str, user_id: int, db: Session) -> list[dict]:
    if agent_type == "forecast":
        return _forecast_recommendations(user_id, db)
    if agent_type == "contract_risk":
        return _contract_risk_recommendations(user_id, db)
    recommendations = _variance_recommendations(user_id, db) + _contract_recommendations(user_id, db)
    recommendations.sort(key=lambda r: r.get("estimated_saving") or 0, reverse=True)
    return recommendations


def _step_to_dict(step: ReactStep) -> dict:
    return {
        "index": step.index,
        "thought": step.thought,
        "tool": step.tool,
        "tool_input": step.tool_input,
        "observation": step.observation,
        "mode": step.mode,
    }


def _react_kwargs(goal: str, user_id: int, db: Session, agent_type: str) -> dict:
    """Shared setup between analyze() (batch) and analyze_stream() (SSE) -
    both run the identical ReAct configuration, just consumed differently."""
    tools = _TOOL_BUILDERS[agent_type](user_id, db)
    return {
        "chat_fn": chat,
        "system_prompt": build_system_prompt(_ROLE_DESCRIPTIONS[agent_type], tools),
        "task_prompt": f"## Goal\n{goal}",
        "tools": tools,
        "initial_observations": None,
        "max_steps": _MAX_STEPS,
        # Prefer native structured tool calls (Groq's `tools=`) over
        # text-parsed Thought/Action/Observation for these multi-tool agents;
        # chat_react.py (single-tool chat) deliberately keeps the
        # text-parsed path instead - see react_engine.py's docstring for why
        # both approaches are worth having.
        "chat_with_tools_fn": chat_with_tools,
    }


def _persist_run(goal: str, user_id: int, agent_type: str, trace: ReactTrace, db: Session) -> AgentRun:
    """Computes the deterministic recommendations and saves the run - shared
    tail end of both analyze() and analyze_stream(), see analyze()'s
    docstring for why the recommendations are computed independently of the
    ReAct trace rather than parsed out of it."""
    recommendations = _compute_recommendations(agent_type, user_id, db)

    run = AgentRun(
        user_id=user_id,
        agent_type=agent_type,
        goal=goal,
        steps_json=json.dumps([_step_to_dict(s) for s in trace.steps], ensure_ascii=False),
        recommendations_json=json.dumps(recommendations, ensure_ascii=False),
        summary=trace.final_answer,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def analyze(goal: str, user_id: int, db: Session, agent_type: str = DEFAULT_AGENT_TYPE) -> AgentRun:
    """Runs one of the three agents (agent_type: "cost_saving", "forecast" or
    "contract_risk") for a goal and persists the result.

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
    """
    trace = run_react(**_react_kwargs(goal, user_id, db, agent_type))
    return _persist_run(goal, user_id, agent_type, trace, db)


def analyze_stream(goal: str, user_id: int, db: Session, agent_type: str = DEFAULT_AGENT_TYPE) -> Iterator[str]:
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
    trace = ReactTrace()
    for step, final_answer in iter_react_steps(**_react_kwargs(goal, user_id, db, agent_type)):
        trace.steps.append(step)
        yield f"event: step\ndata: {json.dumps(_step_to_dict(step), ensure_ascii=False)}\n\n"
        if final_answer is not None:
            trace.final_answer = final_answer

    run = _persist_run(goal, user_id, agent_type, trace, db)
    done_payload = {
        "id": run.id,
        "goal": run.goal,
        "agent_type": run.agent_type,
        "summary": run.summary,
        "recommendations": json.loads(run.recommendations_json or "[]"),
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }
    yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"
