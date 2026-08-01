from __future__ import annotations

from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, LineItem
from app.services import chat_service
from tests.conftest import TestSessionLocal


def test_retrieve_context_fallback_does_not_crash_without_qdrant(db, monkeypatch):
    # chat_service opens its own DB session; point it at the test database.
    monkeypatch.setattr(chat_service, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(chat_service, "qdrant_search", lambda *a, **kw: None)

    doc = Document(user_id=1, filename="f.csv", original_name="toner_invoice.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    item = LineItem(document_id=doc.id, description="HP LaserJet Toner", supplier="Office Depot", total=180.0)
    db.add(item)
    db.commit()

    results = chat_service._retrieve_context("toner", user_id=1)

    assert results
    assert results[0]["source"] == "toner_invoice.csv"
    assert "toner_invoice.csv" in results[0]["text"]


def test_long_conversation_summarizes_old_messages_and_forwards_summary(db, monkeypatch):
    """A conversation past the trigger length must: (1) summarize the
    messages that get dropped (not the ones that stay in context), and
    (2) actually pass that summary into answer_with_react, instead of
    silently discarding it."""
    monkeypatch.setattr(chat_service, "SessionLocal", TestSessionLocal)
    monkeypatch.setattr(chat_service, "qdrant_search", lambda *a, **kw: [])
    monkeypatch.setattr("app.services.ai.chat", lambda messages: "Recap: toner and laptop spend discussed.")

    session = ChatSession(user_id=1)
    db.add(session)
    db.commit()
    db.refresh(session)

    # 21 prior messages, long enough that the 4000-token budget is actually
    # exceeded (short messages would all fit and nothing would be dropped,
    # which is correct behavior but wouldn't exercise this code path).
    long_content = "message about toner cartridges and laptop spend " * 20  # ~250 tokens
    for i in range(21):
        db.add(ChatMessage(session_id=session.id, role="user" if i % 2 == 0 else "assistant",
                            content=f"{i}: {long_content}"))
    db.commit()

    captured = {}

    def fake_answer_with_react(**kwargs):
        captured.update(kwargs)
        return "final answer"

    monkeypatch.setattr(chat_service, "answer_with_react", fake_answer_with_react)

    result = chat_service.answer_question("new question", session.id, user_id=1)

    assert result["reply"] == "final answer"
    assert captured["history_summary"] == "Recap: toner and laptop spend discussed."
    # only the most recent messages remain verbatim in conversation_history
    assert len(captured["conversation_history"]) <= 10

