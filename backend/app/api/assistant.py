from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.assistant import AssistantChatResult, AssistantRequest, AssistantResponse, AssistantSuggestion
from app.services.assistant_router import classify_intent
from app.services.audit_service import log_action
from app.services.chat_service import answer_question

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("", response_model=AssistantResponse)
def route_message(
    payload: AssistantRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
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

    result = answer_question(payload.message, payload.session_id, user.id)
    return AssistantResponse(
        intent="chat",
        method=classification["method"],
        confidence=classification["confidence"],
        chat=AssistantChatResult(**result),
    )
