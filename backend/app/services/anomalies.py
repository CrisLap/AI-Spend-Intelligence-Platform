from __future__ import annotations

import statistics
from collections import defaultdict

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import LineItem
from app.services.i18n_strings import translate as _t

# These reasons are computed once, when a document is processed
# (app/api/documents.py::process_document), and stored on LineItem -
# unlike cost_saving_agent.py's recommendations they aren't re-rendered per
# viewer, so the language in effect is whatever the uploader had selected
# at processing time, not necessarily whoever is currently browsing the
# Anomalies page.
_STRINGS = {
    "en": {
        "price_deviation": "Price {price:.2f} deviates {z:.2f}σ from mean {mean:.2f} of category '{category}'",
        "quantity_deviation": "Quantity {qty:.1f} deviates {z:.2f}σ from mean {mean:.1f} of category '{category}'",
        "within_normal_range": "within normal range",
        "no_items_to_check": "no items to check",
        "no_supplier_to_check": "no supplier to check",
        "new_supplier": "New supplier '{supplier}' not found in historical data for category '{category}'",
        "known_supplier": "known supplier",
        "unknown_category": "unknown",
    },
    "it": {
        "price_deviation": "Il prezzo {price:.2f} devia di {z:.2f}σ dalla media {mean:.2f} della categoria '{category}'",
        "quantity_deviation": "La quantità {qty:.1f} devia di {z:.2f}σ dalla media {mean:.1f} della categoria '{category}'",
        "within_normal_range": "nella norma",
        "no_items_to_check": "nessuna voce da verificare",
        "no_supplier_to_check": "nessun fornitore da verificare",
        "new_supplier": "Nuovo fornitore '{supplier}' non presente nello storico per la categoria '{category}'",
        "known_supplier": "fornitore noto",
        "unknown_category": "sconosciuta",
    },
}


def _zscore_prices(items: list[LineItem], threshold: float, lang: str) -> list[dict]:
    by_cat: dict[str, list[float]] = defaultdict(list)
    for item in items:
        cat = item.category_label or "_all_"
        by_cat[cat].append(item.unit_price)

    stats: dict[str, tuple[float, float]] = {}
    all_prices = [i.unit_price for i in items]
    global_mean = statistics.fmean(all_prices) if all_prices else 0.0
    global_std = statistics.pstdev(all_prices) if len(all_prices) > 1 else 0.0
    for cat, prices in by_cat.items():
        if len(prices) >= 3:
            stats[cat] = (statistics.fmean(prices), statistics.pstdev(prices))
        else:
            stats[cat] = (global_mean, global_std)

    results = []
    for item in items:
        cat = item.category_label or "_all_"
        mean, std = stats[cat]
        z = (item.unit_price - mean) / std if std else 0.0
        is_anom = abs(z) >= threshold
        results.append({
            "type": "price_anomaly",
            "line_item_id": item.id,
            "description": item.description,
            "unit_price": item.unit_price,
            "category": item.category_label,
            "is_anomaly": is_anom,
            "score": round(z, 2),
            "reason": (
                _t(_STRINGS, lang, "price_deviation", price=item.unit_price, z=z, mean=mean, category=cat)
                if is_anom else _t(_STRINGS, lang, "within_normal_range")
            ),
        })
    return results


def _zscore_quantities(items: list[LineItem], threshold: float, lang: str) -> list[dict]:
    by_cat: dict[str, list[float]] = defaultdict(list)
    for item in items:
        cat = item.category_label or "_all_"
        by_cat[cat].append(item.quantity)

    stats: dict[str, tuple[float, float]] = {}
    all_qties = [i.quantity for i in items]
    global_mean = statistics.fmean(all_qties) if all_qties else 0.0
    global_std = statistics.pstdev(all_qties) if len(all_qties) > 1 else 0.0
    for cat, qties in by_cat.items():
        if len(qties) >= 3:
            stats[cat] = (statistics.fmean(qties), statistics.pstdev(qties))
        else:
            stats[cat] = (global_mean, global_std)

    results = []
    for item in items:
        cat = item.category_label or "_all_"
        mean, std = stats[cat]
        z = (item.quantity - mean) / std if std else 0.0
        is_anom = abs(z) >= threshold
        results.append({
            "type": "quantity_anomaly",
            "line_item_id": item.id,
            "description": item.description,
            "quantity": item.quantity,
            "category": item.category_label,
            "is_anomaly": is_anom,
            "score": round(z, 2),
            "reason": (
                _t(_STRINGS, lang, "quantity_deviation", qty=item.quantity, z=z, mean=mean, category=cat)
                if is_anom else _t(_STRINGS, lang, "within_normal_range")
            ),
        })
    return results


def _new_supplier(items: list[LineItem], db: Session, lang: str, threshold_days: int = 90) -> list[dict]:
    item_ids = [i.id for i in items if i.id]
    if not item_ids:
        return [{"type": "new_supplier", "is_anomaly": False, "reason": _t(_STRINGS, lang, "no_items_to_check")} for i in items]

    historical = db.query(LineItem.supplier, LineItem.category_label).filter(
        LineItem.id.notin_(item_ids),
        LineItem.supplier.isnot(None),
        LineItem.supplier != "",
    ).all()
    known_suppliers = {r.supplier.lower() for r in historical}

    results = []
    for item in items:
        if not item.supplier:
            results.append({
                "type": "new_supplier",
                "line_item_id": item.id,
                "description": item.description,
                "supplier": item.supplier,
                "category": item.category_label,
                "is_anomaly": False,
                "score": 0.0,
                "reason": _t(_STRINGS, lang, "no_supplier_to_check"),
            })
        elif item.supplier.lower() not in known_suppliers:
            results.append({
                "type": "new_supplier",
                "line_item_id": item.id,
                "description": item.description,
                "supplier": item.supplier,
                "category": item.category_label,
                "is_anomaly": True,
                "score": 1.0,
                "reason": _t(
                    _STRINGS, lang, "new_supplier",
                    supplier=item.supplier, category=item.category_label or _t(_STRINGS, lang, "unknown_category"),
                ),
            })
        else:
            results.append({
                "type": "new_supplier",
                "line_item_id": item.id,
                "description": item.description,
                "supplier": item.supplier,
                "category": item.category_label,
                "is_anomaly": False,
                "score": 0.0,
                "reason": _t(_STRINGS, lang, "known_supplier"),
            })
    return results


def detect_anomalies(items: list[LineItem], db: Session | None = None, lang: str = "en") -> list[dict]:
    threshold = settings.anomaly_zscore_threshold

    price_results = _zscore_prices(items, threshold, lang)
    qty_results = _zscore_quantities(items, threshold, lang)

    merged: dict[int, dict] = {}
    for r in price_results + qty_results:
        lid = r["line_item_id"]
        if lid not in merged:
            merged[lid] = {
                "line_item_id": lid,
                "description": r["description"],
                "unit_price": r.get("unit_price"),
                "quantity": r.get("quantity"),
                "category": r["category"],
                "is_anomaly": False,
                "anomalies": [],
                "zscore": 0.0,
            }
        merged[lid]["is_anomaly"] = merged[lid]["is_anomaly"] or r["is_anomaly"]
        merged[lid]["unit_price"] = merged[lid]["unit_price"] or r.get("unit_price")
        merged[lid]["quantity"] = merged[lid]["quantity"] or r.get("quantity")
        # Keep the most extreme of the price/quantity z-scores seen for this
        # line item, not just whichever came last - this used to be
        # discarded entirely and overwritten with a flat 0.0 below.
        if abs(r["score"]) > abs(merged[lid]["zscore"]):
            merged[lid]["zscore"] = r["score"]
        if r["is_anomaly"]:
            merged[lid]["anomalies"].append(r["reason"])

    results = list(merged.values())

    if db is not None:
        supplier_results = _new_supplier(items, db, lang)
        for sr in supplier_results:
            lid = sr["line_item_id"]
            if lid is None:
                continue
            if lid in merged:
                merged[lid]["is_anomaly"] = merged[lid]["is_anomaly"] or sr["is_anomaly"]
                if sr["is_anomaly"]:
                    merged[lid]["anomalies"].append(sr["reason"])
            else:
                results.append({
                    "line_item_id": lid,
                    "description": sr["description"],
                    "unit_price": None,
                    "quantity": None,
                    "category": sr["category"],
                    "is_anomaly": sr["is_anomaly"],
                    "anomalies": [sr["reason"]] if sr["is_anomaly"] else [],
                    "zscore": sr.get("score", 0.0),
                })

    for r in results:
        r["reason"] = "; ".join(r["anomalies"]) if r["anomalies"] else _t(_STRINGS, lang, "within_normal_range")

    return results
