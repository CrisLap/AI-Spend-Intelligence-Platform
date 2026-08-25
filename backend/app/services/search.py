from __future__ import annotations

import json

import numpy as np
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document, LineItem
from app.services.ai import cosine_similarity, embed_text
from app.services.vector_store import search as qdrant_search


def _cached_embedding(item: LineItem) -> np.ndarray | None:
    """Read a previously persisted embedding for this line item, if any.
    Returns None on a cache miss or if the stored value is malformed."""
    if not item.embedding_cache:
        return None
    try:
        return np.array(json.loads(item.embedding_cache), dtype=np.float32)
    except (ValueError, TypeError):
        return None


def semantic_search(
    query: str, top_k: int = 10, user_id: int | list[int] | None = None, db: Session | None = None
) -> list[dict]:
    """user_id also accepts a list of ids (the caller's visible role-scope,
    see core/deps.py::get_visible_user_ids) - None means no filter."""
    q_vec = embed_text(query)

    qdrant_hits = qdrant_search(q_vec, top_k=top_k, user_id=user_id)
    if qdrant_hits is not None:
        return [
            {
                "line_item_id": h["line_item_id"],
                "document_id": h.get("document_id"),
                "description": h.get("description"),
                "supplier": h.get("supplier"),
                "total": h.get("total"),
                "category": h.get("category"),
                "score": h["score"],
            }
            for h in qdrant_hits
        ]

    # Qdrant unreachable (e.g. local dev without the container running):
    # fall back to brute-force in-memory cosine similarity over Postgres rows.
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        q = db.query(LineItem).filter(
            LineItem.description.isnot(None),
            LineItem.description != "",
        )
        if user_id is not None:
            q = q.join(Document, LineItem.document_id == Document.id)
            ids = [user_id] if isinstance(user_id, int) else user_id
            q = q.filter(Document.user_id.in_(ids))
        items = q.all()
        scored = []
        cache_dirty = False
        for item in items:
            if not item.description:
                continue
            vec = _cached_embedding(item)
            if vec is None:
                # Cache miss: compute once and persist it, so subsequent
                # searches over the same line item skip re-embedding it.
                vec = embed_text(item.description)
                item.embedding_cache = json.dumps(vec.tolist())
                cache_dirty = True
            sim = cosine_similarity(q_vec, vec)
            scored.append((sim, item))
        if cache_dirty:
            db.commit()
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "line_item_id": item.id,
                "document_id": item.document_id,
                "description": item.description,
                "supplier": item.supplier,
                "total": item.total,
                "category": item.category_label,
                "score": round(sim, 4),
            }
            for sim, item in scored[:top_k]
        ]
    finally:
        if close_db:
            db.close()
