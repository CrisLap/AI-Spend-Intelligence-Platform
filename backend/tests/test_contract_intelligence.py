from __future__ import annotations

from app.core.security import hash_password
from app.models.document import ContractClause, DocType, Document
from app.models.user import User
from app.services import contract_intelligence


def _make_user(db, email: str) -> User:
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_contract(db, owner: User, raw_text: str) -> Document:
    doc = Document(
        user_id=owner.id, filename="c.txt", original_name="c.txt", file_path="/tmp/c.txt",
        doc_type=DocType.contract, raw_text=raw_text,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def test_chunk_text_splits_on_blank_lines():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = contract_intelligence.chunk_text(text)
    assert chunks == ["Paragraph one.", "Paragraph two.", "Paragraph three."]


def test_chunk_text_hard_wraps_oversized_paragraphs():
    long_paragraph = "word " * 500  # far beyond _MAX_CHUNK_CHARS as a single paragraph
    chunks = contract_intelligence.chunk_text(long_paragraph)
    assert len(chunks) > 1
    assert all(len(c) <= contract_intelligence._MAX_CHUNK_CHARS for c in chunks)


def test_chunk_text_empty_input_returns_no_chunks():
    assert contract_intelligence.chunk_text("") == []
    assert contract_intelligence.chunk_text("   \n  \n ") == []


def test_index_contract_persists_one_clause_per_chunk(db, monkeypatch):
    monkeypatch.setattr(contract_intelligence, "upsert_contract_chunk", lambda *a, **kw: False)
    owner = _make_user(db, "contractowner@test.com")
    doc = _make_contract(
        db, owner,
        "Articolo 1 - Oggetto.\n\nArticolo 2 - Rinnovo automatico tacito ogni 12 mesi.",
    )

    clauses = contract_intelligence.index_contract(doc, db)

    assert len(clauses) == 2
    stored = db.query(ContractClause).filter(ContractClause.document_id == doc.id).all()
    assert len(stored) == 2
    assert {c.chunk_index for c in stored} == {0, 1}


def test_reindexing_a_contract_replaces_old_clauses_instead_of_duplicating(db, monkeypatch):
    """Same failure mode as documents.py's line-item re-processing bug this
    project already guards against elsewhere: re-indexing must not pile new
    chunks on top of the old ones."""
    monkeypatch.setattr(contract_intelligence, "upsert_contract_chunk", lambda *a, **kw: False)
    owner = _make_user(db, "reindexowner@test.com")
    doc = _make_contract(db, owner, "Paragraph one.\n\nParagraph two.")

    contract_intelligence.index_contract(doc, db)
    contract_intelligence.index_contract(doc, db)

    stored = db.query(ContractClause).filter(ContractClause.document_id == doc.id).all()
    assert len(stored) == 2


def test_search_contracts_falls_back_to_brute_force_when_qdrant_unreachable(db, monkeypatch):
    monkeypatch.setattr(contract_intelligence, "qdrant_search_contracts", lambda *a, **kw: None)
    monkeypatch.setattr(contract_intelligence, "upsert_contract_chunk", lambda *a, **kw: False)
    owner = _make_user(db, "searchowner@test.com")
    other = _make_user(db, "othercontractowner@test.com")
    doc = _make_contract(
        db, owner,
        "Il contratto si rinnova automaticamente con rinnovo automatico tacito ogni anno.",
    )
    other_doc = _make_contract(db, other, "Testo del tutto scorrelato su forniture di carta.")
    contract_intelligence.index_contract(doc, db)
    contract_intelligence.index_contract(other_doc, db)

    results = contract_intelligence.search_contracts("rinnovo automatico tacito", user_id=owner.id, db=db)

    assert len(results) == 1
    assert results[0]["document_id"] == doc.id
