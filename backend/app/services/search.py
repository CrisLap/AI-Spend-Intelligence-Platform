from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document, LineItem
from app.services.ai import cosine_similarity, embed_text
from app.services.vector_store import search as qdrant_search


def semantic_search(query: str, top_k: int = 10, user_id: int | None = None, db: Session | None = None) -> list[dict]:
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
        if user_id:
            q = q.join(Document, LineItem.document_id == Document.id).filter(Document.user_id == user_id)
        items = q.all()
        scored = []
        for item in items:
            if not item.description:
                continue
            if hasattr(item, "_embedding_cache") and item._embedding_cache:
                vec = item._embedding_cache
            else:
                vec = embed_text(item.description)
            sim = cosine_similarity(q_vec, vec)
            scored.append((sim, item))
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
