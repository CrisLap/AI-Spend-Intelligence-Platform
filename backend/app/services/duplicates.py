from __future__ import annotations

import math

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


def find_duplicates(items: list[LineItem], threshold: float = 0.88, lang: str = "en") -> list[dict]:
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
                continue
            if a.description and b.description:
                sim = cosine_similarity(embed_text(a.description), embed_text(b.description))
                if sim >= threshold and _amounts_close(a.total, b.total):
                    cluster.append(j)
                    cluster_similarities.append(sim)
        if len(cluster) > 1:
            used.update(cluster)
            reason = _t(
                _STRINGS, lang,
                "exact_match" if items[cluster[0]].invoice_number else "similar_match",
            )
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
