from __future__ import annotations

from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import DocType, Document, LineItem, LineItemGroup, LineItemGroupItem


def get_dashboard(user_id: int | None = None, db: Session | None = None) -> dict:
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        q_items = db.query(LineItem)
        q_docs = db.query(Document)
        if user_id is not None:
            q_items = q_items.join(Document).filter(Document.user_id == user_id)
            q_docs = q_docs.filter(Document.user_id == user_id)

        items = q_items.all()
        docs = q_docs.all()
        total_spend = sum(i.total or 0 for i in items)
        total_items = len(items)
        total_docs = len(docs)
        anomaly_count = sum(1 for i in items if i.is_anomaly)

        q_dup_groups = db.query(LineItemGroup.id).distinct()
        if user_id is not None:
            q_dup_groups = (
                db.query(LineItemGroup.id)
                .join(LineItemGroupItem, LineItemGroupItem.group_id == LineItemGroup.id)
                .join(LineItem, LineItem.id == LineItemGroupItem.line_item_id)
                .join(Document, Document.id == LineItem.document_id)
                .filter(Document.user_id == user_id)
                .distinct()
            )
        duplicate_count = q_dup_groups.count()

        by_cat: dict[str, list[float]] = defaultdict(list)
        for i in items:
            cat = i.category_label or "Uncategorized"
            by_cat[cat].append(i.total or 0)
        spend_by_cat = [
            {"category": cat, "total": round(sum(vals), 2), "count": len(vals),
             "percentage": round(sum(vals) / total_spend * 100, 1) if total_spend else 0}
            for cat, vals in sorted(by_cat.items(), key=lambda x: sum(x[1]), reverse=True)
        ]

        by_month: dict[str, list[float]] = defaultdict(list)
        for i in items:
            if i.created_at:
                m = i.created_at.strftime("%Y-%m")
                by_month[m].append(i.total or 0)
        spend_by_month = [
            {"month": m, "total": round(sum(vals), 2), "count": len(vals)}
            for m, vals in sorted(by_month.items())
        ]

        by_supplier: dict[str, list[float]] = defaultdict(list)
        for i in items:
            s = i.supplier or "Unknown"
            by_supplier[s].append(i.total or 0)
        top_suppliers = [
            {"supplier": s, "total": round(sum(vals), 2), "count": len(vals)}
            for s, vals in sorted(by_supplier.items(), key=lambda x: sum(x[1]), reverse=True)[:10]
        ]

        top_cats = sorted(spend_by_cat, key=lambda x: x["total"], reverse=True)[:5]
        return {
            "total_spend": round(total_spend, 2),
            "total_items": total_items,
            "total_documents": total_docs,
            "anomaly_count": anomaly_count,
            "duplicate_count": duplicate_count,
            "spend_by_category": spend_by_cat,
            "spend_by_month": spend_by_month,
            "top_suppliers": top_suppliers,
            "top_categories": top_cats,
        }
    finally:
        if close_db:
            db.close()


def get_supplier_variance(
    user_id: int | None = None, db: Session | None = None, min_items: int = 4
) -> list[dict]:
    """Period-over-period spend variance per supplier: each supplier's line
    items (ordered by created_at) are split in half - the older half is the
    "previous period", the newer half the "recent period" - and the percent
    change in total spend between the two is computed. This works on any
    date range actually present in the data (no fixed calendar year is
    assumed), which matters because demo/real data is rarely a full year
    deep. Suppliers with fewer than min_items line items are skipped: a
    split of 1-2 items isn't a meaningful trend, it's noise.

    Contract documents are excluded: a contract's line item typically
    represents its total face value (a single lump sum), not a recurring
    charge, so mixing it into a period-over-period comparison of actual
    transactional spend would skew the trend rather than reflect it.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        q = (
            db.query(LineItem)
            .join(Document)
            .filter(
                LineItem.supplier.isnot(None),
                LineItem.supplier != "",
                Document.doc_type != DocType.contract,
            )
        )
        if user_id is not None:
            q = q.filter(Document.user_id == user_id)
        items = q.all()

        by_supplier: dict[str, list[LineItem]] = defaultdict(list)
        for i in items:
            by_supplier[i.supplier].append(i)

        results = []
        for supplier, supplier_items in by_supplier.items():
            if len(supplier_items) < min_items:
                continue
            ordered = sorted(supplier_items, key=lambda i: i.created_at or i.id)
            mid = len(ordered) // 2
            previous, recent = ordered[:mid], ordered[mid:]
            previous_total = round(sum(i.total or 0 for i in previous), 2)
            recent_total = round(sum(i.total or 0 for i in recent), 2)
            if previous_total <= 0:
                continue
            variance_pct = round((recent_total - previous_total) / previous_total * 100, 1)
            results.append({
                "supplier": supplier,
                "previous_total": previous_total,
                "recent_total": recent_total,
                "variance_pct": variance_pct,
                "previous_count": len(previous),
                "recent_count": len(recent),
                "categories": sorted({i.category_label for i in supplier_items if i.category_label}),
            })

        results.sort(key=lambda r: abs(r["variance_pct"]), reverse=True)
        return results
    finally:
        if close_db:
            db.close()
