from __future__ import annotations

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
