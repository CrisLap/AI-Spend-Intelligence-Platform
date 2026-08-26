from __future__ import annotations

import json
import math

import numpy as np

from app.models.document import LineItem
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
