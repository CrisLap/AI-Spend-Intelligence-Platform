"""
Seed the database with realistic demo data for AI Spend Intelligence Platform.

Creates 3 demo users and 8 processed documents (invoices/orders) spread over
the last ~6 months, covering 7 of the 13 spend categories. The data is
deliberately constructed - and verified against the actual detection logic,
not just "plausible" - to trigger every detection module on first login:

  - Modulo 5 (Duplicate Detection): the same toner cartridge line appears
    twice on the same Office Depot invoice (same supplier + invoice number
    + amount -> exact match).
  - Modulo 6 (Anomaly Detection): a workstation invoiced at ~7x the price of
    otherwise near-identical laptops (price anomaly, verified to clear the
    default 2.5 z-score threshold even with a small sample); an order for
    500 pens against a baseline of 4-6 units (quantity anomaly); a
    first-time invoice from a supplier never seen before (new-supplier
    anomaly).

Descriptions are written in Italian (as real invoices in this context would
be) but each one keeps at least one of the classifier's rule-based English
keywords (toner, paper, laptop, consulting, ...) so that classification is
deterministic and correct even when Ollama isn't running - the embedding
fallback used otherwise is a non-semantic hash and would categorize these
essentially at random.

Usage:
    cd backend
    python scripts/seed_demo_data.py            # seed (skips if already present)
    python scripts/seed_demo_data.py --reset    # wipe existing demo data first

Requires DATABASE_URL to be reachable (same as the running app). Ollama and
Qdrant are optional - classification and embeddings fall back to the
deterministic offline methods already built into the app if they aren't
running, and Qdrant indexing is skipped (not failed) if unreachable.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.document import (  # noqa: E402
    DocType,
    Document,
    DocumentStatus,
    LineItem,
    LineItemGroup,
    LineItemGroupItem,
)
from app.models.user import User  # noqa: E402
from app.services.ai import embed_text  # noqa: E402
from app.services.anomalies import detect_anomalies  # noqa: E402
from app.services.audit_service import log_action  # noqa: E402
from app.services.classifier import classify_batch  # noqa: E402
from app.services.duplicates import find_duplicates  # noqa: E402
from app.services.vector_store import upsert_line_item  # noqa: E402

DEMO_MARKER_EMAIL = "demo.admin@spendintel.io"

DEMO_USERS = [
    {"email": "demo.admin@spendintel.io", "full_name": "Alessia Ferrari", "role": "admin", "password": "DemoPass123!"},
    {"email": "demo.buyer@spendintel.io", "full_name": "Marco Colombo", "role": "buyer", "password": "DemoPass123!"},
    {"email": "demo.finance@spendintel.io", "full_name": "Giulia Bianchi", "role": "finance", "password": "DemoPass123!"},
]

# (filename, doc_type, months_ago, invoice_number, supplier, [(description, qty, unit_price)])
# Row-level supplier/invoice_number can be overridden with a 4th/5th tuple
# element; otherwise they default to the document-level values above.
DOCUMENTS = [
    # --- Baseline: a one-time historical import, establishing every
    # recurring supplier as "known" so that only the genuinely new one
    # (QuickFix, below) triggers the new-supplier anomaly - otherwise every
    # supplier's very first appearance would trigger it, drowning out the
    # one deliberate example.
    (
        "storico_spese_importazione.csv", "invoice", 6, None, None,
        [
            ("Toner cartridge HP LaserJet 415A - riordino ordinario", 3, 44.00, "Office Depot", "IMPORT-01"),
            ("Laptop Dell Latitude 5540 - acquisto standard", 2, 895.00, "Dell Technologies", "IMPORT-02"),
            ("Abbonamento cloud storage AWS - subscription mensile", 1, 600.00, "CloudNet Solutions", "IMPORT-03"),
            ("Consulenza legale societaria - consulting advisory annuale", 1, 8000.00, "Deloitte Consulting", "IMPORT-04"),
            ("Sedia ergonomica ufficio - chair furniture standard", 4, 195.00, "Arredo Ufficio Spa", "IMPORT-05"),
            ("Corso di onboarding nuovi assunti - training hr", 5, 110.00, "SkillUp Academy", "IMPORT-06"),
            ("Manutenzione ordinaria impianti - maintenance annuale", 1, 1200.00, "ClimaTech Impianti", "IMPORT-07"),
        ],
    ),
    (
        "fattura_office_depot_consolidato.csv", "invoice", 5, "OD-2026-0417", "Office Depot",
        [
            ("Toner cartridge HP LaserJet 415A", 4, 45.00),
            ("Toner cartridge HP LaserJet 415A", 4, 45.00),  # accidental duplicate row
            ("Risme di carta bianca A4 - paper standard ufficio", 5, 22.50),
            ("Penne a sfera blu conf. 50pz", 5, 12.00),
            ("Punti metallici per cucitrice - stapler refill", 6, 4.20),
            ("Toner cartridge stampante Canon multifunzione", 4, 52.00),
            ("Materiale di stationery vario per ufficio", 6, 8.90),
            ("Risme di carta riciclata A4 - paper premium", 5, 23.50),
            ("Penne a sfera blu - riordino urgente magazzino", 500, 0.35),  # quantity anomaly
        ],
    ),
    (
        "ordine_dell_trimestrale.csv", "order", 4, "DELL-88350", "Dell Technologies",
        [
            ("Laptop Dell Latitude 5540 per ufficio commerciale", 1, 899.00),
            ("Laptop Dell Latitude 5540 per ufficio commerciale", 1, 900.00),
            ("Laptop Dell Latitude 5540 per ufficio commerciale", 1, 901.00),
            ("Notebook HP EliteBook 840 per team vendite", 1, 899.00),
            ("Notebook HP EliteBook 840 per team vendite", 1, 900.00),
            ("Notebook HP EliteBook 840 per team vendite", 1, 901.00),
            ("Laptop Lenovo ThinkPad T14 per sviluppo", 1, 899.00),
            ("Laptop Lenovo ThinkPad T14 per sviluppo", 1, 900.00),
            ("Laptop Dell Precision 7680 workstation mobile ingegneria", 1, 6000.00),  # price anomaly
        ],
    ),
    (
        "abbonamento_cloudnet.csv", "invoice", 4, "CN-2026-091", "CloudNet Solutions",
        [
            ("Abbonamento cloud storage AWS - subscription mensile", 1, 640.00),
            ("Licenza Microsoft 365 Business Premium - license software", 25, 18.90),
        ],
    ),
    (
        "fattura_deloitte_q1.csv", "invoice", 3, "DEL-Q1-2026", "Deloitte Consulting",
        [
            ("Consulenza strategica trimestrale - consulting advisory Q1 2026", 1, 18500.00),
        ],
    ),
    (
        "fattura_quickfix_it.csv", "invoice", 2, "QF-0091", "QuickFix IT Consulting Srl",
        [
            ("Servizio di audit finanziario annuale - audit consulting", 1, 3200.00),  # new-supplier anomaly
        ],
    ),
    (
        "fattura_arredo_ufficio.csv", "invoice", 1, "ARR-2201", "Arredo Ufficio Spa",
        [
            ("Sedia ergonomica ufficio - chair furniture direzionale", 12, 210.00),
            ("Scrivania regolabile in altezza - desk furniture open space", 6, 340.00),
        ],
    ),
    (
        "fattura_formazione_leadership.csv", "invoice", 1, "TR-3390", "SkillUp Academy",
        [
            ("Corso di formazione leadership per manager - training hr", 15, 120.00),
        ],
    ),
    (
        "fattura_manutenzione_hvac.csv", "invoice", 0, "HVAC-771", "ClimaTech Impianti",
        [
            ("Manutenzione impianto HVAC sede centrale - maintenance", 1, 1450.00),
        ],
    ),
]

DOC_TYPE_MAP = {"invoice": DocType.invoice, "order": DocType.order, "contract": DocType.contract}


def _months_ago(n: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=30 * n + random.randint(0, 6))


def wipe_demo_data(db) -> None:
    emails = [u["email"] for u in DEMO_USERS]
    users = db.query(User).filter(User.email.in_(emails)).all()
    user_ids = [u.id for u in users]
    if not user_ids:
        return
    doc_ids = [d.id for d in db.query(Document.id).filter(Document.user_id.in_(user_ids)).all()]
    item_ids = [i.id for i in db.query(LineItem.id).filter(LineItem.document_id.in_(doc_ids)).all()]
    group_ids = [
        g.group_id
        for g in db.query(LineItemGroupItem.group_id).filter(LineItemGroupItem.line_item_id.in_(item_ids)).distinct()
    ]
    db.query(LineItemGroupItem).filter(LineItemGroupItem.line_item_id.in_(item_ids)).delete(synchronize_session=False)
    db.query(LineItemGroup).filter(LineItemGroup.id.in_(group_ids)).delete(synchronize_session=False)
    db.query(LineItem).filter(LineItem.document_id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()
    print(f"Wiped {len(doc_ids)} documents, {len(item_ids)} line items, {len(users)} demo users.")


def seed(db) -> None:
    users = {}
    for u in DEMO_USERS:
        user = User(
            email=u["email"],
            full_name=u["full_name"],
            role=u["role"],
            hashed_password=hash_password(u["password"]),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        users[u["email"]] = user
        log_action(db, user_id=user.id, action="register", entity_type="user", entity_id=user.id, details={"seed": True})

    buyer = users["demo.buyer@spendintel.io"]

    for filename, dtype, months_ago, invoice_number, supplier, rows in DOCUMENTS:
        created = _months_ago(months_ago)
        doc = Document(
            user_id=buyer.id,
            filename=filename,
            original_name=filename,
            doc_type=DOC_TYPE_MAP[dtype],
            status=DocumentStatus.processing,
            file_path=f"./data/uploads/{filename}",
            file_size_bytes=random.randint(2000, 50000),
            created_at=created,
            updated_at=created,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        items = []
        for row in rows:
            desc, qty, unit_price = row[0], row[1], row[2]
            row_supplier = row[3] if len(row) > 3 else supplier
            row_invoice = row[4] if len(row) > 4 else invoice_number
            item = LineItem(
                document_id=doc.id,
                description=desc,
                quantity=qty,
                unit_price=unit_price,
                total=round(qty * unit_price, 2),
                supplier=row_supplier,
                invoice_number=row_invoice,
                invoice_date=created.strftime("%Y-%m-%d"),
                created_at=created,
            )
            db.add(item)
            items.append(item)
        db.commit()
        for item in items:
            db.refresh(item)

        classifications = classify_batch([i.description for i in items])
        for item, cls in zip(items, classifications):
            item.category_label = cls["category"]
            item.category_unspsc = cls.get("unspsc", "")
            item.confidence = cls["confidence"]
            item.classification_method = cls["method"]

        anomalies = detect_anomalies(items, db=db)
        for item, anom in zip(items, anomalies):
            item.is_anomaly = anom["is_anomaly"]
            item.anomaly_reason = anom["reason"]
            item.anomaly_score = anom["zscore"]
        db.commit()

        for item in items:
            upsert_line_item(
                item.id,
                embed_text(item.description),
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

        for g in find_duplicates(items):
            grp = LineItemGroup(reason=g["reason"], similarity=g["similarity"])
            db.add(grp)
            db.commit()
            for gi in g["items"]:
                li = next((it for it in items if it.id == gi["id"]), None)
                if li:
                    db.add(LineItemGroupItem(group_id=grp.id, line_item_id=li.id))
            db.commit()

        doc.status = DocumentStatus.classified
        db.commit()

        flagged = [i for i in items if i.is_anomaly]
        dup_note = " [+ duplicate detected]" if find_duplicates(items) else ""
        anomaly_note = f" [+ {len(flagged)} anomaly flagged]" if flagged else ""
        print(f"  seeded {filename} - {len(items)} line items, supplier: {supplier}{dup_note}{anomaly_note}")

    log_action(
        db, user_id=buyer.id, action="upload_document", entity_type="document",
        details={"seed": True, "documents": len(DOCUMENTS)},
    )

    print("\nDone. Log in with any of:")
    for u in DEMO_USERS:
        print(f"  {u['email']} / {u['password']}  (role: {u['role']})")
    print("\nTry: the dashboard (spend by month/category/supplier), Duplicates,")
    print("Anomalies, semantic search ('toner HP'), and the chat ('quanto abbiamo")
    print("speso in consulenza?').")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data for AI Spend Intelligence Platform")
    parser.add_argument("--reset", action="store_true", help="Delete existing demo data before reseeding")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.email == DEMO_MARKER_EMAIL).first()
        if existing and not args.reset:
            print(f"Demo data already present (user {DEMO_MARKER_EMAIL} exists). Use --reset to wipe and reseed.")
            return
        if existing and args.reset:
            wipe_demo_data(db)
        seed(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
