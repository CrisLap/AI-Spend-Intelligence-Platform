from __future__ import annotations

import logging

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from qdrant_client.http.exceptions import UnexpectedResponse

from app.core.config import settings
from app.services.ai import EMBEDDING_DIM

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None
_collection_ready = False


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=5.0,
        )
    return _client


def ensure_collection() -> bool:
    """Create the collection if it doesn't exist yet.

    Returns False (instead of raising) if Qdrant is unreachable, so callers
    can fall back to another retrieval strategy (offline/dev environments
    without Qdrant running).
    """
    global _collection_ready
    if _collection_ready:
        return True
    try:
        client = get_client()
        existing = {c.name for c in client.get_collections().collections}
        if settings.qdrant_collection not in existing:
            client.create_collection(
                collection_name=settings.qdrant_collection,
                vectors_config=qmodels.VectorParams(
                    size=EMBEDDING_DIM, distance=qmodels.Distance.COSINE
                ),
            )
        _collection_ready = True
        return True
    except Exception:
        logger.warning("Qdrant unavailable at %s, falling back to in-memory search", settings.qdrant_url)
        return False


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
    except (Exception, UnexpectedResponse):
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


def search(vector: np.ndarray, top_k: int = 10, user_id: int | None = None) -> list[dict] | None:
    """Vector search against Qdrant.

    Returns None (not an empty list) when Qdrant is unreachable, so callers
    can distinguish "no results" from "fall back to brute-force search".
    """
    if not ensure_collection():
        return None
    try:
        query_filter = None
        if user_id is not None:
            query_filter = qmodels.Filter(
                must=[qmodels.FieldCondition(key="user_id", match=qmodels.MatchValue(value=user_id))]
            )
        hits = get_client().search(
            collection_name=settings.qdrant_collection,
            query_vector=vector.tolist(),
            query_filter=query_filter,
            limit=top_k,
        )
        return [{"line_item_id": h.id, "score": round(h.score, 4), **h.payload} for h in hits]
    except Exception:
        logger.exception("Qdrant search failed, falling back to in-memory search")
        return None
