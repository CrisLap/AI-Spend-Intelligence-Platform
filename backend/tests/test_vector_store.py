from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np

from app.services import vector_store


def _reset_module_state():
    vector_store._client = None
    vector_store._collection_ready_at = {}


def test_search_returns_none_when_qdrant_unreachable():
    """No Qdrant running (e.g. CI/local without the container): callers must
    get None (not an empty list) so they know to fall back."""
    _reset_module_state()
    vec = np.zeros(vector_store.EMBEDDING_DIM if hasattr(vector_store, "EMBEDDING_DIM") else 768, dtype=np.float32)
    result = vector_store.search(vec, top_k=5)
    assert result is None


def test_upsert_returns_false_when_qdrant_unreachable():
    _reset_module_state()
    vec = np.ones(768, dtype=np.float32)
    ok = vector_store.upsert_line_item(1, vec, payload={"description": "test"})
    assert ok is False


def test_delete_line_items_does_not_raise_when_unreachable():
    _reset_module_state()
    vector_store.delete_line_items([1, 2, 3])  # should swallow the connection error


def test_ensure_collection_creates_when_missing(monkeypatch):
    _reset_module_state()
    fake_client = MagicMock()
    fake_client.get_collections.return_value = MagicMock(collections=[])
    monkeypatch.setattr(vector_store, "get_client", lambda: fake_client)

    ok = vector_store.ensure_collection()

    assert ok is True
    fake_client.create_collection.assert_called_once()


def test_search_formats_hits_with_mocked_client(monkeypatch):
    _reset_module_state()
    fake_client = MagicMock()
    fake_client.get_collections.return_value = MagicMock(
        collections=[MagicMock(name="spend_documents")]
    )
    fake_client.get_collections.return_value.collections = []
    hit = MagicMock(id=42, score=0.91, payload={"description": "HP toner", "supplier": "HP"})
    fake_client.search.return_value = [hit]
    monkeypatch.setattr(vector_store, "get_client", lambda: fake_client)

    vec = np.ones(768, dtype=np.float32)
    results = vector_store.search(vec, top_k=3, user_id=1)

    assert results == [
        {"line_item_id": 42, "score": 0.91, "description": "HP toner", "supplier": "HP"}
    ]


def test_search_handles_hit_with_none_payload(monkeypatch):
    """A point with no payload (partial write, or inserted by another
    process) must not crash the whole search with a TypeError."""
    _reset_module_state()
    fake_client = MagicMock()
    fake_client.get_collections.return_value = MagicMock(collections=[])
    hit = MagicMock(id=7, score=0.5, payload=None)
    fake_client.search.return_value = [hit]
    monkeypatch.setattr(vector_store, "get_client", lambda: fake_client)

    vec = np.ones(768, dtype=np.float32)
    results = vector_store.search(vec, top_k=3)

    assert results == [{"line_item_id": 7, "score": 0.5}]


def test_ensure_collection_cache_expires_and_rechecks(monkeypatch):
    """A permanently-cached 'ready' result would mean a later outage (e.g.
    the collection disappearing) goes undetected until process restart."""
    _reset_module_state()
    fake_client = MagicMock()
    fake_client.get_collections.return_value = MagicMock(collections=[])
    monkeypatch.setattr(vector_store, "get_client", lambda: fake_client)
    monkeypatch.setattr(vector_store, "_COLLECTION_READY_TTL_SECONDS", 0)

    assert vector_store.ensure_collection() is True
    assert vector_store.ensure_collection() is True
    # get_collections must be called again once the cache has expired, not
    # just once ever.
    assert fake_client.get_collections.call_count == 2


def test_get_client_does_not_deadlock_when_called_from_ensure_collection(monkeypatch):
    """ensure_collection() holds _init_lock and calls get_client(), which
    also acquires _init_lock - this must not deadlock (regression test for
    using a non-reentrant Lock)."""
    _reset_module_state()
    monkeypatch.setattr(vector_store, "QdrantClient", lambda **kw: MagicMock(
        get_collections=lambda: MagicMock(collections=[])
    ))

    ok = vector_store.ensure_collection()

    assert ok is True