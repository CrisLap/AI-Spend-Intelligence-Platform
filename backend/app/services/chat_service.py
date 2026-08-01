from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, LineItem
from app.services.ai import cosine_similarity, embed_text
from app.services.chat_react import answer_with_react
from app.services.vector_store import search as qdrant_search

_MAX_HISTORY_TOKENS = 4000
_SUMMARY_TRIGGER_LENGTH = 20


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _trim_history(messages: list[ChatMessage]) -> list[ChatMessage]:
    total = 0
    trimmed = []
    for m in reversed(messages):
        tokens = _estimate_tokens(m.content or "")
        if total + tokens > _MAX_HISTORY_TOKENS:
            break
        total += tokens
        trimmed.append(m)
    return list(reversed(trimmed))


def _summarize_history(older_messages: list[ChatMessage], db: Session, session: ChatSession) -> str:
    """Summarize the portion of history that is about to be dropped from
    context (not the most recent messages, which stay in context verbatim).
    Builds on any existing summary so it stays a rolling recap as the
    conversation keeps growing, instead of only covering the latest cut."""
    if not older_messages:
        return session.summary or ""
    text = "\n".join(f"{m.role}: {m.content[:200]}" for m in older_messages)
    prompt = "Summarize this spend analysis conversation briefly, in 2-3 sentences."
    if session.summary:
        prompt += f"\nExisting summary so far: {session.summary}"
    prompt += f"\nAdditional earlier messages to fold in:\n{text}"
    from app.services.ai import chat as llm_chat
    summary = llm_chat([{"role": "user", "content": prompt}])
    if summary and not summary.startswith("[Offline]"):
        session.summary = summary[:500]
        db.commit()
    return session.summary or ""


def _retrieve_context(query: str, top_k: int = 8, user_id: int | None = None) -> list[dict]:
    q_vec = embed_text(query)

    qdrant_hits = qdrant_search(q_vec, top_k=top_k, user_id=user_id)
    if qdrant_hits is not None:
        return [
            {
                "text": f"[{h.get('source')}] {h.get('description')} - {h.get('supplier')} - €{h.get('total')} - {h.get('category')}",
                "score": h["score"],
                "source": h.get("source"),
                "supplier": h.get("supplier"),
                "total": h.get("total"),
            }
            for h in qdrant_hits
        ]

    # Qdrant unreachable: fall back to brute-force in-memory retrieval.
    db = SessionLocal()
    try:
        q = (
            db.query(LineItem, Document.original_name)
            .join(Document, LineItem.document_id == Document.id)
            .filter(LineItem.description.isnot(None), LineItem.description != "")
        )
        if user_id is not None:
            q = q.filter(Document.user_id == user_id)
        rows = q.all()
        scored = []
        for item, doc_name in rows:
            vec = embed_text(item.description)
            sim = cosine_similarity(q_vec, vec)
            scored.append((sim, item, doc_name))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "text": f"[{doc_name}] {item.description} - {item.supplier} - €{item.total} - {item.category_label}",
                "score": round(sim, 4),
                "source": doc_name,
                "supplier": item.supplier,
                "total": item.total,
            }
            for sim, item, doc_name in scored[:top_k]
        ]
    finally:
        db.close()


def answer_question(message: str, session_id: int | None, user_id: int) -> dict:
    db: Session = SessionLocal()
    try:
        if session_id is None:
            session = ChatSession(user_id=user_id)
            db.add(session)
            db.commit()
            db.refresh(session)
        else:
            session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
            if session is None or session.user_id != user_id:
                session = ChatSession(user_id=user_id)
                db.add(session)
                db.commit()
                db.refresh(session)

        db.add(ChatMessage(session_id=session.id, role="user", content=message))
        db.commit()

        history = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == session.id)
            .order_by(ChatMessage.created_at)
            .all()
        )

        summary_text = ""
        if len(history) > _SUMMARY_TRIGGER_LENGTH:
            kept = _trim_history(history)
            kept_ids = {m.id for m in kept}
            older = [m for m in history if m.id not in kept_ids]
            summary_text = _summarize_history(older, db, session)
            history = kept

        context = _retrieve_context(message, user_id=user_id)

        history_dicts = [
            {"role": m.role, "content": m.content} for m in history[-10:]
        ]

        reply = answer_with_react(
            message=message,
            context=context,
            conversation_history=history_dicts,
            retrieve_fn=lambda q: _retrieve_context(q, user_id=user_id),
            history_summary=summary_text or None,
        )

        msg = ChatMessage(
            session_id=session.id,
            role="assistant",
            content=reply,
            sources_json=json.dumps(context, ensure_ascii=False),
        )
        db.add(msg)
        db.commit()

        return {
            "reply": reply,
            "sources": [{"text": c["text"], "score": c["score"], "source": c["source"]} for c in context],
            "session_id": session.id,
        }
    finally:
        db.close()
