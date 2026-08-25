from __future__ import annotations

import logging
import threading
import time

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import settings
from app.services.ai import EMBEDDING_DIM

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None
_collection_ready_at: dict[str, float] = {}
_COLLECTION_READY_TTL_SECONDS = 60
_init_lock = threading.RLock()


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        with _init_lock:
            if _client is None:  # re-check inside the lock (double-checked locking)
                _client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key,
                    timeout=5.0,
                )
    return _client


def _ensure(collection_name: str) -> bool:
    """Create the given collection if it doesn't exist yet.

    Returns False (instead of raising) if Qdrant is unreachable, so callers
    can fall back to another retrieval strategy (offline/dev environments
    without Qdrant running).

    The "ready" result is cached briefly per collection (not forever) - a
    permanent cache would mean that once Qdrant is confirmed reachable, a
    later outage (e.g. the collection disappearing after a restart with
    ephemeral storage) would go undetected until the process itself
    restarts, with every upsert/search/delete silently failing against a
    stale assumption in the meantime.
    """
    now = time.monotonic()
    ready_at = _collection_ready_at.get(collection_name)
    if ready_at is not None and now - ready_at < _COLLECTION_READY_TTL_SECONDS:
        return True
    with _init_lock:
        # Re-check after acquiring the lock: another thread may have just
        # refreshed this while we were waiting.
        now = time.monotonic()
        ready_at = _collection_ready_at.get(collection_name)
        if ready_at is not None and now - ready_at < _COLLECTION_READY_TTL_SECONDS:
            return True
        try:
            client = get_client()
            existing = {c.name for c in client.get_collections().collections}
            if collection_name not in existing:
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE
                    ),
                )
            _collection_ready_at[collection_name] = time.monotonic()
            return True
        except Exception:
            logger.warning("Qdrant unavailable at %s, falling back to in-memory search", settings.qdrant_url)
            _collection_ready_at.pop(collection_name, None)
            return False


def ensure_collection() -> bool:
    return _ensure(settings.qdrant_collection)


def upsert_line_item(line_item_id: int, vector: np.ndarray, payload: dict) -> bool:
    if not ensure_collection():
        return False
    try:
        get_client().upsert(
            collection_name=settings.qdrant_collection,
            points=[
                qmodels.PointStruct(id=line_item_id, vector=vector.tolist(), payload=payload)
            ],
        )
        return True
    except Exception:
        logger.exception("Failed to upsert line item %s into Qdrant", line_item_id)
        return False


def delete_line_items(line_item_ids: list[int]) -> None:
    if not line_item_ids or not ensure_collection():
        return
    try:
        get_client().delete(
            collection_name=settings.qdrant_collection,
            points_selector=qmodels.PointIdsList(points=line_item_ids),
        )
    except Exception:
        logger.exception("Failed to delete line items %s from Qdrant", line_item_ids)


def _user_id_filter(user_id: int | list[int] | None) -> qmodels.Filter | None:
    """user_id accepts a single id, a list of ids (the caller's visible
    role-scope, see core/deps.py::get_visible_user_ids), or None (no
    filter - admin, or an internal unscoped call)."""
    if user_id is None:
        return None
    if isinstance(user_id, int):
        return qmodels.Filter(
            must=[qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=user_id))]
        )
    return qmodels.Filter(
        must=[qmodels.FieldCondition(key="user_id", match=qmodels.MatchAny(any=user_id))]
    )


def search(vector: np.ndarray, top_k: int = 10, user_id: int | list[int] | None = None) -> list[dict] | None:
    """Vector search against Qdrant.

    Returns None (not an empty list) when Qdrant is unreachable, so callers
    can distinguish "no results" from "fall back to brute-force search".
    """
    if not ensure_collection():
        return None
    try:
        query_filter = _user_id_filter(user_id)
        hits = get_client().search(
            collection_name=settings.qdrant_collection,
            query_vector=vector.tolist(),
            query_filter=query_filter,
            limit=top_k,
        )
        return [{"line_item_id": h.id, "score": round(h.score, 4), **(h.payload or {})} for h in hits]
    except Exception:
        logger.exception("Qdrant search failed, falling back to in-memory search")
        return None


def upsert_contract_chunk(chunk_id: int, vector: np.ndarray, payload: dict) -> bool:
    """Same as upsert_line_item but against the separate contract-chunk
    collection, so contract-clause point ids (their own DB primary key)
    never collide with line-item point ids in the main collection."""
    if not _ensure(settings.qdrant_contract_collection):
        return False
    try:
        get_client().upsert(
            collection_name=settings.qdrant_contract_collection,
            points=[
                qmodels.PointStruct(id=chunk_id, vector=vector.tolist(), payload=payload)
            ],
        )
        return True
    except Exception:
        logger.exception("Failed to upsert contract chunk %s into Qdrant", chunk_id)
        return False


def delete_contract_chunks(chunk_ids: list[int]) -> None:
    if not chunk_ids or not _ensure(settings.qdrant_contract_collection):
        return
    try:
        get_client().delete(
            collection_name=settings.qdrant_contract_collection,
            points_selector=qmodels.PointIdsList(points=chunk_ids),
        )
    except Exception:
        logger.exception("Failed to delete contract chunks %s from Qdrant", chunk_ids)


def search_contracts(vector: np.ndarray, top_k: int = 5, user_id: int | list[int] | None = None) -> list[dict] | None:
    """Vector search against the contract-chunk collection. Returns None
    (not an empty list) when Qdrant is unreachable, matching search()'s
    contract so callers can tell "unreachable" from "no results"."""
    if not _ensure(settings.qdrant_contract_collection):
        return None
    try:
        query_filter = _user_id_filter(user_id)
        hits = get_client().search(
            collection_name=settings.qdrant_contract_collection,
            query_vector=vector.tolist(),
            query_filter=query_filter,
            limit=top_k,
        )
        return [{"chunk_id": h.id, "score": round(h.score, 4), **(h.payload or {})} for h in hits]
    except Exception:
        logger.exception("Qdrant contract search failed, falling back to in-memory search")
        return None
