from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models.agent_run import AgentRun
from app.services.agents.react_engine import build_system_prompt, run_react
from app.services.agents.tools import build_tools
from app.services.ai import chat
from app.services.analytics import get_supplier_variance
from app.services.contract_intelligence import search_contracts

_MAX_STEPS = 4

_ROLE_DESCRIPTION = (
    "You are the AI Cost Saving Agent for a corporate spend intelligence "
    "platform. Given a goal, investigate the company's real spend data step "
    "by step - checking spend overview, supplier variance, anomalies and "
    "contract terms as needed - before concluding. Only state figures you "
    "actually retrieved via a tool; never invent numbers."
)

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


def analyze(goal: str, user_id: int, db: Session) -> AgentRun:
    """Runs the Cost Saving Agent for a goal and persists the result.

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
    """
    tools = build_tools(user_id, db)
    system_prompt = build_system_prompt(_ROLE_DESCRIPTION, tools)
    task_prompt = f"## Goal\n{goal}"

    trace = run_react(
        chat_fn=chat,
        system_prompt=system_prompt,
        task_prompt=task_prompt,
        tools=tools,
        initial_observations=None,
        max_steps=_MAX_STEPS,
    )

    recommendations = _variance_recommendations(user_id, db) + _contract_recommendations(user_id, db)
    recommendations.sort(key=lambda r: r.get("estimated_saving") or 0, reverse=True)

    steps_payload = [
        {
            "index": s.index,
            "thought": s.thought,
            "tool": s.tool,
            "tool_input": s.tool_input,
            "observation": s.observation,
        }
        for s in trace.steps
    ]

    run = AgentRun(
        user_id=user_id,
        goal=goal,
        steps_json=json.dumps(steps_payload, ensure_ascii=False),
        recommendations_json=json.dumps(recommendations, ensure_ascii=False),
        summary=trace.final_answer,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
