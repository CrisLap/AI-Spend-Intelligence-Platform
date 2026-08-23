from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_ui_language
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.assistant import AssistantChatResult, AssistantRequest, AssistantResponse, AssistantSuggestion
from app.services.assistant_router import classify_intent
from app.services.audit_service import log_action
from app.services.chat_service import answer_question, answer_question_stream

router = APIRouter(prefix="/assistant", tags=["assistant"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=AssistantResponse)
@limiter.limit("20/minute")
def route_message(
    request: Request,
    payload: AssistantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    lang: str = Depends(get_ui_language),
):
    """Single entry point that classifies the message's intent and routes
    it to the RAG chat or hands off to the Cost Saving Agent family.

    Deliberately does NOT run the agent inline for a "cost_saving" intent:
    the agent's ReAct loop takes several seconds and the frontend already
    has a dedicated Cost Saving Agent page with live SSE step rendering -
    duplicating that UI inside the chat page would be redundant. Instead
    this returns a `suggestion` (agent_type + goal) the frontend uses to
    hand the user off to that page, prefilled and ready to run.
    """
    classification = classify_intent(payload.message)
    log_action(
        db, user_id=user.id, action="assistant_route", entity_type="assistant",
        details={
            "intent": classification["intent"],
            "agent_type": classification["agent_type"],
            "method": classification["method"],
        },
    )

    if classification["intent"] == "cost_saving":
        return AssistantResponse(
            intent="cost_saving",
            method=classification["method"],
            confidence=classification["confidence"],
            suggestion=AssistantSuggestion(
                agent_type=classification["agent_type"] or "cost_saving",
                goal=payload.message,
            ),
        )

    result = answer_question(payload.message, payload.session_id, user.id, lang=lang)
    return AssistantResponse(
        intent="chat",
        method=classification["method"],
        confidence=classification["confidence"],
        chat=AssistantChatResult(**result),
    )


@router.get("/stream")
@limiter.limit("20/minute")
def route_message_stream(
    request: Request,
    message: str = Query(..., min_length=1, max_length=4000),
    session_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    lang: str = Depends(get_ui_language),
):
    """SSE equivalent of POST /assistant. A plain GET with query params (not
    EventSource) is used deliberately - same rationale as
    cost_saving.py::analyze_cost_saving_stream: EventSource can't send the
    Authorization header this app's auth relies on everywhere else, so the
    frontend reads this via fetch() + ReadableStream instead.

    A "cost_saving" intent still doesn't run inline (see route_message's
    docstring) - it streams a single `event: suggestion` and closes, so the
    frontend's handling of that case is identical whether it came from the
    batch or streaming entry point.

    DO NOT convert this to POST: it would break the SSE streaming contract
    with the frontend's fetch()+ReadableStream reader. This endpoint does
    write an audit log entry despite being a GET - see the rationale
    above; that's a deliberate, documented tradeoff, not an oversight.
    """
    classification = classify_intent(message)
    log_action(
        db, user_id=user.id, action="assistant_route", entity_type="assistant",
        details={
            "intent": classification["intent"],
            "agent_type": classification["agent_type"],
            "method": classification["method"],
        },
    )

    if classification["intent"] == "cost_saving":
        suggestion_payload = {
            "agent_type": classification["agent_type"] or "cost_saving",
            "goal": message,
        }

        def suggestion_source():
            yield f"event: suggestion\ndata: {json.dumps(suggestion_payload, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            suggestion_source(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    return StreamingResponse(
        answer_question_stream(message, session_id, user.id, lang=lang),
        media_type="text/event-stream", headers={"Cache-Control": "no-cache"},
    )
