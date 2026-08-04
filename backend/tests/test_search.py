from __future__ import annotations

from app.core.security import hash_password
from app.models.document import Document, LineItem
from app.models.user import User
from app.services import search as search_module
from app.services.search import semantic_search


def _make_user(db, email: str, user_id: int | None = None) -> User:
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    if user_id is not None:
        u.id = user_id
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_item(db, owner: User, description: str) -> LineItem:
    doc = Document(user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    item = LineItem(document_id=doc.id, description=description, supplier="Acme", total=100.0)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_semantic_search_isolates_by_user_even_when_user_id_is_zero(db, monkeypatch):
    """user_id=0 must not be treated as 'no filter' - it's a valid id and
    the old `if user_id:` check silently leaked every user's data for it."""
    monkeypatch.setattr(search_module, "qdrant_search", lambda *a, **kw: None)

    owner = _make_user(db, "owner@test.com", user_id=0)
    other = _make_user(db, "other@test.com")
    _make_item(db, owner, "Toner HP LaserJet for owner")
    _make_item(db, other, "Toner HP LaserJet for other user")

    results = semantic_search("toner", user_id=owner.id, db=db)

    assert len(results) == 1
    assert "owner" in results[0]["description"]


def test_semantic_search_caches_embedding_after_first_lookup(db, monkeypatch):
    """The embedding for a line item should only ever be computed once -
    a second search over the same item must reuse the persisted cache."""
    monkeypatch.setattr(search_module, "qdrant_search", lambda *a, **kw: None)

    owner = _make_user(db, "cacheowner@test.com")
    item = _make_item(db, owner, "Laptop Dell Precision workstation")

    calls = {"n": 0}
    real_embed_text = search_module.embed_text

    def counting_embed_text(text):
        calls["n"] += 1
        return real_embed_text(text)

    monkeypatch.setattr(search_module, "embed_text", counting_embed_text)

    assert item.embedding_cache is None

    semantic_search("laptop", user_id=owner.id, db=db)
    calls_after_first = calls["n"]
    assert calls_after_first >= 1

    db.refresh(item)
    assert item.embedding_cache is not None

    semantic_search("laptop", user_id=owner.id, db=db)
    # The query embedding itself is still computed each time; what must NOT
    # happen again is re-embedding the (unchanged) line item description.
    assert calls["n"] == calls_after_first + 1
