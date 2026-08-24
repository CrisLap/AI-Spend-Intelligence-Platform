from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_ui_language
from app.core.rate_limit import limiter
from app.models.chat import ChatMessage, ChatSession
from app.models.user import User
from app.schemas.chat import ChatMessageOut, ChatRequest, ChatResponse, ChatSessionOut
from app.services.audit_service import log_action
from app.services.chat_service import answer_question

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=ChatResponse)
@limiter.limit("20/minute")
def chat(
    request: Request, payload: ChatRequest, user: User = Depends(get_current_user), lang: str = Depends(get_ui_language)
):
    return answer_question(payload.message, payload.session_id, user.id, lang=lang)


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).filter(
        ChatSession.user_id == user.id
    ).order_by(ChatSession.updated_at.desc()).limit(50).all()

    # One batched query for the first user message of every session (used
    # as a title preview), instead of a per-session query - see the
    # list_duplicates N+1 note in known-issues.md for why that matters.
    previews: dict[int, str] = {}
    session_ids = [s.id for s in sessions]
    if session_ids:
        first_ids = (
            db.query(func.min(ChatMessage.id))
            .filter(ChatMessage.session_id.in_(session_ids), ChatMessage.role == "user")
            .group_by(ChatMessage.session_id)
            .scalar_subquery()
        )
        first_messages = db.query(ChatMessage.session_id, ChatMessage.content).filter(
            ChatMessage.id.in_(first_ids)
        ).all()
        previews = {session_id: content[:80] for session_id, content in first_messages}

    out = []
    for s in sessions:
        item = ChatSessionOut.model_validate(s)
        item.preview = previews.get(s.id) or (s.summary[:80] if s.summary else None)
        out.append(item)
    return out


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_messages(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user.id
    ).first()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    msgs = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.created_at).all()
    return [ChatMessageOut.model_validate(m) for m in msgs]


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id, ChatSession.user_id == user.id
    ).first()
    if not session:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Session not found")
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete(synchronize_session=False)
    db.delete(session)
    db.commit()
    log_action(db, user_id=user.id, action="delete_chat_session", entity_type="chat_session", entity_id=session_id)
