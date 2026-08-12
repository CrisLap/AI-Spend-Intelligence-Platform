from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.agent_run import AgentRun
from app.models.user import User
from app.schemas.cost_saving import AgentRunOut, AgentRunRequest
from app.services.audit_service import log_action
from app.services.cost_saving_agent import analyze

router = APIRouter(prefix="/cost-saving", tags=["cost-saving"])


def _to_out(run: AgentRun) -> AgentRunOut:
    return AgentRunOut(
        id=run.id,
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
    run = analyze(payload.goal, user.id, db)
    log_action(
        db, user_id=user.id, action="cost_saving_analyze", entity_type="agent_run", entity_id=run.id,
        details={"goal": payload.goal, "recommendation_count": len(json.loads(run.recommendations_json or "[]"))},
    )
    return _to_out(run)


@router.get("/history", response_model=list[AgentRunOut])
def list_history(
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    runs = (
        db.query(AgentRun)
        .filter(AgentRun.user_id == user.id)
        .order_by(AgentRun.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
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
