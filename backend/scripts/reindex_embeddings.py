"""
Recompute every LineItem/ContractClause embedding and re-upsert it into
Qdrant, using whichever provider embed_text() currently resolves to
(Ollama, then Jina, then the offline hash fallback - see app/services/ai.py).

Needed once after JINA_API_KEY is configured in production: rows embedded
earlier with the offline hash fallback live in the same Qdrant collection
as rows embedded with a real model, and cosine similarity between a
hash-embedded vector and a real one is essentially noise - mixing them
degrades ranking for the older rows until they're recomputed.

Usage:
    cd backend
    python scripts/reindex_embeddings.py

Requires DATABASE_URL (and, to actually get real embeddings instead of the
hash fallback, JINA_API_KEY or a reachable OLLAMA_HOST) to be set the same
way the running app expects.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.models.document import ContractClause, Document, LineItem  # noqa: E402
from app.services.ai import embed_text  # noqa: E402
from app.services.vector_store import upsert_contract_chunk, upsert_line_item  # noqa: E402


def reindex_line_items(db) -> int:
    rows = db.query(LineItem, Document).join(Document, LineItem.document_id == Document.id).all()
    count = 0
    for item, doc in rows:
        if not item.description:
            continue
        vector = embed_text(item.description)
        item.embedding_cache = json.dumps(vector.tolist())
        upsert_line_item(
            item.id,
            vector,
            payload={
                "document_id": doc.id,
                "user_id": doc.user_id,
                "description": item.description,
                "supplier": item.supplier,
                "total": item.total,
                "category": item.category_label,
                "source": doc.original_name,
            },
        )
        count += 1
        if count % 20 == 0:
            db.commit()
            print(f"  ...{count} line items reindexed")
    db.commit()
    return count


def reindex_contract_clauses(db) -> int:
    rows = (
        db.query(ContractClause, Document)
        .join(Document, ContractClause.document_id == Document.id)
        .all()
    )
    count = 0
    for clause, doc in rows:
        if not clause.text:
            continue
        vector = embed_text(clause.text)
        clause.embedding_cache = json.dumps(vector.tolist())
        upsert_contract_chunk(
            clause.id,
            vector,
            payload={
                "document_id": doc.id,
                "user_id": doc.user_id,
                "chunk_index": clause.chunk_index,
                "text": clause.text,
                "source": doc.original_name,
            },
        )
        count += 1
    db.commit()
    return count


def main() -> None:
    db = SessionLocal()
    try:
        print("Reindexing line items...")
        n_items = reindex_line_items(db)
        print(f"Done: {n_items} line items reindexed.")

        print("Reindexing contract clauses...")
        n_clauses = reindex_contract_clauses(db)
        print(f"Done: {n_clauses} contract clauses reindexed.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
