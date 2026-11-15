from __future__ import annotations

import json
import math

import numpy as np
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.document import Document, LineItem, LineItemGroup, LineItemGroupItem
from app.services.ai import cosine_similarity, embed_text
from app.services.i18n_strings import translate as _t

# Computed once at document-processing time (app/api/documents.py) and
# stored on LineItemGroup - same "fixed at generation time" caveat as
# anomalies.py's reasons, see that module's comment for why.
_STRINGS = {
    "en": {
        "exact_match": "same supplier + invoice + amount",
        "similar_match": "similar description + matching amount",
    },
    "it": {
        "exact_match": "stesso fornitore + fattura + importo",
        "similar_match": "descrizione simile + importo corrispondente",
    },
}


def _amounts_close(a: float, b: float, rel_tol: float = 0.02) -> bool:
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=0.01)


def _cached_embedding(item: LineItem) -> np.ndarray | None:
    """Read a previously persisted embedding for this line item, if any -
    same cache format/convention as search.py's helper of the same name."""
    if not item.embedding_cache:
        return None
    try:
        return np.array(json.loads(item.embedding_cache), dtype=np.float32)
    except (ValueError, TypeError):
        return None


def find_duplicates(items: list[LineItem], threshold: float = 0.88, lang: str = "en") -> list[dict]:
    # Embed each item once up front (reusing/populating embedding_cache the
    # way search.py does) instead of re-embedding on every pairwise
    # comparison in the O(n^2) loop below - this used to re-embed the same
    # description many times over as the item list grew. Indexed by
    # position (not item.id) since callers aren't guaranteed to pass
    # already-persisted rows with unique ids.
    vectors: list[np.ndarray | None] = []
    for item in items:
        if not item.description:
            vectors.append(None)
            continue
        vec = _cached_embedding(item)
        if vec is None:
            vec = embed_text(item.description)
            item.embedding_cache = json.dumps(vec.tolist())
        vectors.append(vec)

    groups = []
    used = set()
    for i in range(len(items)):
        if i in used:
            continue
        cluster = [i]
        # Real similarity of each joined item to the anchor - an exact match
        # is 1.0 by definition, a semantic match keeps its actual cosine
        # score, instead of the group always being reported as 100% similar
        # even when it was only an approximate match.
        cluster_similarities: list[float] = []
        # Whether each joined member matched via the exact-fields path (True)
        # or only via cosine similarity (False) - the group's reason must
        # reflect the weakest path actually used, not just the anchor's own
        # fields (a cluster can be anchored by an item with an invoice
        # number while another member only matched via similarity).
        cluster_exact: list[bool] = [True]
        for j in range(i + 1, len(items)):
            if j in used:
                continue
            a, b = items[i], items[j]
            same_desc = (
                a.description and b.description
                and a.description.strip().lower() == b.description.strip().lower()
            )
            exact = (
                a.supplier and a.invoice_number and same_desc
                and a.supplier == b.supplier
                and a.invoice_number == b.invoice_number
                and _amounts_close(a.total, b.total)
            )
            if exact:
                cluster.append(j)
                cluster_similarities.append(1.0)
                cluster_exact.append(True)
                continue
            vec_a, vec_b = vectors[i], vectors[j]
            if vec_a is not None and vec_b is not None:
                sim = cosine_similarity(vec_a, vec_b)
                if sim >= threshold and _amounts_close(a.total, b.total):
                    cluster.append(j)
                    cluster_similarities.append(sim)
                    cluster_exact.append(False)
        if len(cluster) > 1:
            used.update(cluster)
            reason = _t(_STRINGS, lang, "exact_match" if all(cluster_exact) else "similar_match")
            groups.append({
                "reason": reason,
                # Report the weakest link in the cluster, not an
                # optimistic/fake 1.0 - a conservative, honest figure.
                "similarity": round(min(cluster_similarities), 4) if cluster_similarities else 1.0,
                "items": [{
                    "id": items[k].id,
                    "description": items[k].description,
                    "supplier": items[k].supplier,
                    "total": items[k].total,
                    "invoice_number": items[k].invoice_number,
                } for k in cluster],
            })
    return groups


def visible_group_ids(db: Session, scope: int | list[int] | None, search: str | None = None):
    """Ids of duplicate groups (LineItemGroup) that contain at least one
    line item within `scope` (see core/deps.py::get_visible_user_ids - None
    means no filter/admin). Shared by GET /duplicates, PATCH
    /duplicates/{id}/resolve and the MCP list_duplicates tool."""
    q = (
        db.query(LineItemGroupItem.group_id)
        .join(LineItem, LineItemGroupItem.line_item_id == LineItem.id)
        .join(Document, LineItem.document_id == Document.id)
    )
    if scope is not None:
        ids = [scope] if isinstance(scope, int) else scope
        q = q.filter(Document.user_id.in_(ids))
    if search:
        like = f"%{search}%"
        q = q.filter(or_(LineItem.description.ilike(like), LineItem.supplier.ilike(like)))
    return q.distinct()


def list_duplicates_for(
    db: Session,
    scope: int | list[int] | None,
    skip: int = 0,
    limit: int = 50,
    search: str | None = None,
    include_resolved: bool = False,
) -> list[dict]:
    """Query already-grouped duplicate clusters restricted to `scope` -
    shared by GET /duplicates (api/duplicates.py) and the MCP
    list_duplicates tool so the visibility filter lives in exactly one
    place. Two batched IN(...) queries for the whole page instead of one
    query per group plus one per item in that group."""
    own_group_ids = visible_group_ids(db, scope, search)
    query = db.query(LineItemGroup).filter(LineItemGroup.id.in_(own_group_ids))
    if not include_resolved:
        query = query.filter(LineItemGroup.resolved == False)  # noqa: E712
    groups = query.order_by(LineItemGroup.created_at.desc()).offset(skip).limit(limit).all()
    group_ids = [g.id for g in groups]

    links = (
        db.query(LineItemGroupItem).filter(LineItemGroupItem.group_id.in_(group_ids)).all()
        if group_ids else []
    )
    links_by_group: dict[int, list[int]] = {}
    for link in links:
        links_by_group.setdefault(link.group_id, []).append(link.line_item_id)

    line_item_ids = [link.line_item_id for link in links]
    items_by_id: dict[int, LineItem] = {}
    if line_item_ids:
        item_query = (
            db.query(LineItem)
            .join(Document, LineItem.document_id == Document.id)
            .filter(LineItem.id.in_(line_item_ids))
        )
        if scope is not None:
            ids = [scope] if isinstance(scope, int) else scope
            item_query = item_query.filter(Document.user_id.in_(ids))
        items_by_id = {item.id: item for item in item_query.all()}

    result = []
    for g in groups:
        group_items = []
        for line_item_id in links_by_group.get(g.id, []):
            item = items_by_id.get(line_item_id)
            if item:
                group_items.append({
                    "id": item.id,
                    "description": item.description,
                    "supplier": item.supplier,
                    "total": item.total,
                    "invoice_number": item.invoice_number,
                })
        result.append({
            "id": g.id,
            "reason": g.reason,
            "similarity": g.similarity,
            "items": group_items,
            "resolved": g.resolved,
        })
    return result
