from __future__ import annotations

import json
import re

import numpy as np
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import ContractClause, Document
from app.services.ai import cosine_similarity, embed_text
from app.services.vector_store import search_contracts as qdrant_search_contracts
from app.services.vector_store import upsert_contract_chunk

_MAX_CHUNK_CHARS = 800


def chunk_text(raw_text: str) -> list[str]:
    """Split contract text into paragraph-sized chunks so semantic search can
    return a specific clause instead of the whole document. Splits on blank
    lines first (natural paragraph breaks), then hard-wraps any paragraph
    still longer than _MAX_CHUNK_CHARS so a single huge block of text
    doesn't become one unsearchable chunk."""
    if not raw_text or not raw_text.strip():
        return []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]
    chunks: list[str] = []
    for p in paragraphs:
        if len(p) <= _MAX_CHUNK_CHARS:
            chunks.append(p)
            continue
        for i in range(0, len(p), _MAX_CHUNK_CHARS):
            chunks.append(p[i : i + _MAX_CHUNK_CHARS])
    return chunks


def index_contract(document: Document, db: Session) -> list[ContractClause]:
    """Chunk + embed a contract document's raw text and upsert each chunk
    into the contract Qdrant collection. Existing chunks for this document
    are replaced (not appended) so re-processing doesn't duplicate them."""
    existing = db.query(ContractClause).filter(ContractClause.document_id == document.id).all()
    if existing:
        from app.services.vector_store import delete_contract_chunks
        delete_contract_chunks([c.id for c in existing])
        for c in existing:
            db.delete(c)
        db.commit()

    chunks = chunk_text(document.raw_text or "")
    saved: list[ContractClause] = []
    for idx, text in enumerate(chunks):
        clause = ContractClause(document_id=document.id, chunk_index=idx, text=text)
        db.add(clause)
        db.commit()
        db.refresh(clause)
        vector = embed_text(text)
        clause.embedding_cache = json.dumps(vector.tolist())
        db.commit()
        upsert_contract_chunk(
            clause.id,
            vector,
            payload={
                "document_id": document.id,
                "user_id": document.user_id,
                "chunk_index": idx,
                "text": text,
                "source": document.original_name,
            },
        )
        saved.append(clause)
    return saved


def search_contracts(
    query: str, top_k: int = 5, user_id: int | list[int] | None = None, db: Session | None = None
) -> list[dict]:
    """Semantic search over contract clauses. Qdrant-first, falling back to
    brute-force in-memory cosine similarity over Postgres rows if Qdrant is
    unreachable - same pattern as search.py::semantic_search."""
    q_vec = embed_text(query)

    hits = qdrant_search_contracts(q_vec, top_k=top_k, user_id=user_id)
    if hits is not None:
        return [
            {
                "chunk_id": h["chunk_id"],
                "document_id": h.get("document_id"),
                "text": h.get("text"),
                "source": h.get("source"),
                "score": h["score"],
            }
            for h in hits
        ]

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        q = db.query(ContractClause).join(Document, ContractClause.document_id == Document.id)
        if user_id is not None:
            ids = [user_id] if isinstance(user_id, int) else user_id
            q = q.filter(Document.user_id.in_(ids))
        rows = q.with_entities(ContractClause, Document.original_name).all()
        scored = []
        cache_dirty = False
        for clause, source_name in rows:
            vec = None
            if clause.embedding_cache:
                try:
                    vec = np.array(json.loads(clause.embedding_cache), dtype=np.float32)
                except (ValueError, TypeError):
                    vec = None
            if vec is None:
                vec = embed_text(clause.text)
                clause.embedding_cache = json.dumps(vec.tolist())
                cache_dirty = True
            scored.append((cosine_similarity(q_vec, vec), clause, source_name))
        if cache_dirty:
            db.commit()
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "chunk_id": clause.id,
                "document_id": clause.document_id,
                "text": clause.text,
                "source": source_name,
                "score": round(sim, 4),
            }
            for sim, clause, source_name in scored[:top_k]
        ]
    finally:
        if close_db:
            db.close()
