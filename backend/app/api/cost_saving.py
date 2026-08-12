from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.cost_saving import AgentRunOut, AgentRunRequest
from app.services.audit_service import log_action
from app.services.cost_saving_agent import AGENT_TYPES, analyze, analyze_stream

router = APIRouter(prefix="/cost-saving", tags=["cost-saving"])


def _validate_agent_type(agent_type: str) -> str:
    if agent_type not in AGENT_TYPES:
        raise HTTPException(status_code=400, detail=f"agent_type must be one of {list(AGENT_TYPES)}")
    return agent_type


def _to_out(run: AgentRun) -> AgentRunOut:
    return AgentRunOut(
        id=run.id,
        agent_type=run.agent_type,
        goal=run.goal,
        summary=run.summary or "",
        steps=json.loads(run.steps_json) if run.steps_json else [],
        recommendations=json.loads(run.recommendations_json) if run.recommendations_json else [],
        created_at=run.created_at,
    )


@router.post("/analyze", response_model=AgentRunOut)
def analyze_cost_saving(
    payload: AgentRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    agent_type = _validate_agent_type(payload.agent_type)
    run = analyze(payload.goal, user.id, db, agent_type=agent_type)
    log_action(
        db, user_id=user.id, action="cost_saving_analyze", entity_type="agent_run", entity_id=run.id,
        details={
            "goal": payload.goal,
            "agent_type": agent_type,
            "recommendation_count": len(json.loads(run.recommendations_json or "[]")),
        },
    )
    return _to_out(run)


@router.get("/analyze/stream")
def analyze_cost_saving_stream(
    goal: str = "Trova opportunità di risparmio",
    agent_type: str = "cost_saving",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """SSE equivalent of POST /analyze: emits one `event: step` per ReAct
    step as it happens, then a final `event: done` with the persisted run
    (same shape POST /analyze returns). A plain GET with a query param
    (not EventSource) is used deliberately: EventSource can't send the
    `Authorization: Bearer` header this app's auth relies on everywhere
    else, and a query-string token would leak into browser history/server
    logs - the frontend instead reads this stream with `fetch()` +
    `ReadableStream`, which does support custom headers.
    """
    agent_type = _validate_agent_type(agent_type)

    def event_source():
        last_chunk = ""
        for chunk in analyze_stream(goal, user.id, db, agent_type=agent_type):
            last_chunk = chunk
            yield chunk
        if last_chunk.startswith("event: done"):
            try:
                payload = json.loads(last_chunk.split("data: ", 1)[1])
                log_action(
                    db, user_id=user.id, action="cost_saving_analyze", entity_type="agent_run",
                    entity_id=payload.get("id"),
                    details={
                        "goal": goal,
                        "agent_type": agent_type,
                        "recommendation_count": len(payload.get("recommendations", [])),
                        "stream": True,
                    },
                )
            except (IndexError, ValueError):
                pass

    return StreamingResponse(
        event_source(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.get("/history", response_model=list[AgentRunOut])
def list_history(
    skip: int = 0,
    limit: int = 20,
    agent_type: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(AgentRun).filter(AgentRun.user_id == user.id)
    if agent_type is not None:
        query = query.filter(AgentRun.agent_type == _validate_agent_type(agent_type))
    runs = query.order_by(AgentRun.created_at.desc()).offset(skip).limit(limit).all()
    return [_to_out(r) for r in runs]


@router.get("/history/{run_id}", response_model=AgentRunOut)
def get_history_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    run = db.query(AgentRun).filter(AgentRun.id == run_id, AgentRun.user_id == user.id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return _to_out(run)
