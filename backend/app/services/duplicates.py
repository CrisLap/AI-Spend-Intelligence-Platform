from __future__ import annotations

import math

from app.models.document import LineItem
from app.services.ai import cosine_similarity, embed_text


def _amounts_close(a: float, b: float, rel_tol: float = 0.02) -> bool:
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=0.01)


def find_duplicates(items: list[LineItem], threshold: float = 0.88) -> list[dict]:
    groups = []
    used = set()
    for i in range(len(items)):
        if i in used:
            continue
        cluster = [i]
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
                continue
            if a.description and b.description:
                sim = cosine_similarity(embed_text(a.description), embed_text(b.description))
                if sim >= threshold and _amounts_close(a.total, b.total):
                    cluster.append(j)
        if len(cluster) > 1:
            used.update(cluster)
            reason = (
                "same supplier + invoice + amount"
                if items[cluster[0]].invoice_number
                else "similar description + matching amount"
            )
            groups.append({
                "reason": reason,
                "similarity": 1.0,
                "items": [{
                    "id": items[k].id,
                    "description": items[k].description,
                    "supplier": items[k].supplier,
                    "total": items[k].total,
                    "invoice_number": items[k].invoice_number,
                } for k in cluster],
            })
    return groups
