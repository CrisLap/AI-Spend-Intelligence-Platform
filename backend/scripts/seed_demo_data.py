"""
Seed the database with realistic demo data for AI Spend Intelligence Platform.

Creates 3 demo users and 9 processed documents (invoices/orders) spread over
the last ~6 months, covering 7 of the 13 spend categories. Each document's
source CSV is also written to disk under UPLOAD_DIR, matching the row-level
data seeded in the database, so features that read from disk (e.g. the
"reprocess document" endpoint) work against real files instead of a
dangling path reference. The data is deliberately constructed - and
verified against the actual detection logic, not just "plausible" - to
trigger every detection module on first login:

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

Also seeded, for the Cost Saving Agent module:

  - Supplier spend variance: CloudNet Solutions and Deloitte Consulting each
    get enough additional invoices, spread across the seed window, that
    their spend clearly rises between the older and newer half of their
    history - verified below (see the assertions in seed()) to clear the
    20% variance threshold in cost_saving_agent.py, so
    analytics.get_supplier_variance() surfaces them deterministically
    instead of by chance.
  - Contract clauses: two doc_type=contract documents get realistic
    Italian contract text (set directly on Document.raw_text and indexed
    via contract_intelligence.index_contract(), since this script builds
    documents directly rather than through the /documents/process
    endpoint) containing an explicit auto-renewal and early-termination
    penalty clause. The exact phrasing was checked against the offline
    hash-embedding fallback (see contract_intelligence.py) to actually
    clear the Cost Saving Agent's similarity threshold even without Ollama
    running, not just written to "look right".

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
import csv
import random
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings  # noqa: E402
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.agent_run import AgentRun  # noqa: E402
from app.models.audit import AuditLog  # noqa: E402
from app.models.chat import ChatMessage, ChatSession  # noqa: E402
from app.models.document import (  # noqa: E402
    ContractClause,
    DocType,
    Document,
    DocumentStatus,
    LineItem,
    LineItemGroup,
    LineItemGroupItem,
)
from app.models.feedback import Feedback  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.ai import embed_text  # noqa: E402
from app.services.analytics import get_supplier_variance  # noqa: E402
from app.services.anomalies import detect_anomalies  # noqa: E402
from app.services.audit_service import log_action  # noqa: E402
from app.services.classifier import classify_batch  # noqa: E402
from app.services.contract_intelligence import index_contract, search_contracts  # noqa: E402
from app.services.cost_saving_agent import _VARIANCE_THRESHOLD_PCT  # noqa: E402
from app.services.duplicates import find_duplicates  # noqa: E402
from app.services.vector_store import delete_contract_chunks, upsert_line_item  # noqa: E402

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
    # --- Cost Saving Agent: extra CloudNet Solutions and Deloitte Consulting
    # invoices so each supplier has >=4 line items spread across the seed
    # window, with a clear, deterministic spend increase between the older
    # and newer half of their history (see get_supplier_variance()).
    (
        "abbonamento_cloudnet_q2.csv", "invoice", 2, "CN-2026-140", "CloudNet Solutions",
        [
            ("Abbonamento cloud storage AWS - subscription mensile", 1, 950.00),
            ("Licenza Microsoft 365 Business Premium - license software", 30, 18.90),
        ],
    ),
    (
        "abbonamento_cloudnet_recente.csv", "invoice", 0, "CN-2026-205", "CloudNet Solutions",
        [
            ("Abbonamento cloud storage AWS - subscription mensile", 1, 1050.00),
            ("Storage aggiuntivo cloud backup - subscription cloud", 1, 300.00),
        ],
    ),
    (
        "fattura_deloitte_q2.csv", "invoice", 1, "DEL-Q2-2026", "Deloitte Consulting",
        [
            ("Consulenza strategica trimestrale - consulting advisory Q2 2026", 1, 25000.00),
        ],
    ),
    (
        "fattura_deloitte_extra.csv", "invoice", 0, "DEL-EX-2026", "Deloitte Consulting",
        [
            ("Servizio di due diligence acquisizione - consulting advisory straordinario", 1, 12000.00),
        ],
    ),
]

# (filename, months_ago, invoice_number, supplier, annual_value, raw_text)
# Contract documents: unlike DOCUMENTS above, these carry full contract text
# (Document.raw_text) that gets chunked and indexed by
# contract_intelligence.index_contract() so the Cost Saving Agent's
# contract_search tool has real clauses to find - not just a line item.
CONTRACTS = [
    (
        "contratto_cloudnet_solutions.txt", 5, "CTR-CN-2025", "CloudNet Solutions", 11400.00,
        """ARTICOLO 1 - OGGETTO
Il presente contratto disciplina la fornitura di servizi di cloud storage e licenze software da CloudNet Solutions al cliente per l'intera durata contrattuale.

ARTICOLO 5 - RINNOVO
RINNOVO AUTOMATICO TACITO: il contratto si rinnova automaticamente (tacito rinnovo automatico) ogni 12 mesi salvo disdetta scritta da inviare almeno 90 giorni prima della scadenza naturale.

ARTICOLO 6 - RECESSO
PENALE RECESSO ANTICIPATO: in caso di recesso anticipato da parte del cliente e' prevista una penale pari al 20% del valore residuo del contratto.""",
    ),
    (
        "contratto_climatech_impianti.txt", 5, "CTR-CT-2025", "ClimaTech Impianti", 1450.00,
        """ARTICOLO 1 - OGGETTO
Il presente contratto disciplina il servizio di manutenzione ordinaria e straordinaria degli impianti HVAC presso la sede del cliente.

ARTICOLO 4 - RINNOVO
RINNOVO AUTOMATICO TACITO: il contratto si rinnova automaticamente (tacito rinnovo automatico) ogni 12 mesi salvo disdetta scritta da inviare almeno 60 giorni prima della scadenza naturale.

ARTICOLO 7 - RECESSO
PENALE RECESSO ANTICIPATO: in caso di recesso anticipato da parte del cliente e' prevista una penale pari al 15% del valore residuo del contratto.""",
    ),
]

DOC_TYPE_MAP = {"invoice": DocType.invoice, "order": DocType.order, "contract": DocType.contract}


def _write_demo_file(filename: str, supplier: str | None, invoice_number: str | None, rows: list) -> tuple[str, int]:
    """Write the CSV backing a seeded document to disk, so that features
    reading from doc.file_path (e.g. the /process re-run endpoint) work
    against real data instead of a dangling reference."""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    path = upload_dir / filename
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["description", "quantity", "unit_price", "total", "supplier", "invoice_number"])
        for row in rows:
            desc, qty, price = row[0], row[1], row[2]
            row_supplier = row[3] if len(row) > 3 else supplier
            row_invoice = row[4] if len(row) > 4 else invoice_number
            w.writerow([desc, qty, price, round(qty * price, 2), row_supplier, row_invoice])
    return str(path), path.stat().st_size


def _months_ago(n: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=30 * n + random.randint(0, 6))


def wipe_demo_data(db) -> None:
    emails = [u["email"] for u in DEMO_USERS]
    users = db.query(User).filter(User.email.in_(emails)).all()
    user_ids = [u.id for u in users]
    if not user_ids:
        return
    docs = db.query(Document).filter(Document.user_id.in_(user_ids)).all()
    doc_ids = [d.id for d in docs]
    for d in docs:
        try:
            Path(d.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    item_ids = [i.id for i in db.query(LineItem.id).filter(LineItem.document_id.in_(doc_ids)).all()]
    group_ids = [
        g.group_id
        for g in db.query(LineItemGroupItem.group_id).filter(LineItemGroupItem.line_item_id.in_(item_ids)).distinct()
    ]
    clause_ids = [
        c.id for c in db.query(ContractClause.id).filter(ContractClause.document_id.in_(doc_ids)).all()
    ]
    session_ids = [
        s.id for s in db.query(ChatSession.id).filter(ChatSession.user_id.in_(user_ids)).all()
    ]

    # Delete in dependency order (children before parents) so this works
    # against real foreign key constraints (e.g. Postgres/Neon), not just
    # SQLite's default lax enforcement.
    db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.id.in_(session_ids)).delete(synchronize_session=False)
    db.query(Feedback).filter(
        (Feedback.user_id.in_(user_ids)) | (Feedback.document_id.in_(doc_ids))
    ).delete(synchronize_session=False)
    db.query(LineItemGroupItem).filter(LineItemGroupItem.line_item_id.in_(item_ids)).delete(synchronize_session=False)
    db.query(LineItemGroup).filter(LineItemGroup.id.in_(group_ids)).delete(synchronize_session=False)
    db.query(LineItem).filter(LineItem.document_id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(ContractClause).filter(ContractClause.document_id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(AgentRun).filter(AgentRun.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.user_id.in_(user_ids)).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
    db.commit()
    delete_contract_chunks(clause_ids)
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
        file_path, file_size = _write_demo_file(filename, supplier, invoice_number, rows)
        doc = Document(
            user_id=buyer.id,
            filename=filename,
            original_name=filename,
            doc_type=DOC_TYPE_MAP[dtype],
            status=DocumentStatus.processing,
            file_path=file_path,
            file_size_bytes=file_size,
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

    for filename, months_ago, contract_number, supplier, annual_value, raw_text in CONTRACTS:
        created = _months_ago(months_ago)
        file_path, file_size = _write_demo_file(
            filename, supplier, contract_number, [("Valore contrattuale annuale", 1, annual_value)]
        )
        doc = Document(
            user_id=buyer.id,
            filename=filename,
            original_name=filename,
            doc_type=DocType.contract,
            status=DocumentStatus.processing,
            file_path=file_path,
            file_size_bytes=file_size,
            raw_text=raw_text,
            created_at=created,
            updated_at=created,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        item = LineItem(
            document_id=doc.id,
            description=f"Contratto annuale {supplier} - {contract_number}",
            quantity=1,
            unit_price=annual_value,
            total=annual_value,
            supplier=supplier,
            invoice_number=contract_number,
            invoice_date=created.strftime("%Y-%m-%d"),
            created_at=created,
        )
        db.add(item)
        db.commit()

        clauses = index_contract(doc, db)
        doc.status = DocumentStatus.classified
        db.commit()
        print(f"  seeded {filename} - contract for {supplier}, {len(clauses)} clauses indexed")

    log_action(
        db, user_id=buyer.id, action="upload_document", entity_type="document",
        details={"seed": True, "documents": len(DOCUMENTS) + len(CONTRACTS)},
    )

    # Verify the Cost Saving Agent's data (not just "plausible", checked
    # against the actual functions it calls) actually surfaces what the
    # docstring above promises, the same way the anomaly/duplicate seed
    # rows are verified against detect_anomalies()/find_duplicates().
    variances = get_supplier_variance(user_id=buyer.id, db=db)
    triggered = [v for v in variances if v["variance_pct"] >= _VARIANCE_THRESHOLD_PCT]
    if triggered:
        print("\nCost Saving Agent - supplier variance check:")
        for v in triggered:
            print(f"  {v['supplier']}: {v['variance_pct']:+.1f}% (threshold {_VARIANCE_THRESHOLD_PCT}%)")
    else:
        print(
            "\nWARNING: no supplier cleared the variance threshold - "
            "the Cost Saving Agent demo won't have a renegotiation recommendation to show."
        )

    contract_hits = search_contracts("rinnovo automatico tacito", top_k=5, user_id=buyer.id, db=db)
    matched = [h for h in contract_hits if h["score"] >= 0.55]
    if matched:
        print("Cost Saving Agent - contract clause check:")
        for h in matched:
            print(f"  {h.get('source')}: score {h['score']:.3f}")
    else:
        print(
            "WARNING: no contract clause cleared the similarity threshold - "
            "the Cost Saving Agent demo won't have a contract-renewal recommendation to show."
        )

    print("\nDone. Log in with any of:")
    for u in DEMO_USERS:
        print(f"  {u['email']} / {u['password']}  (role: {u['role']})")
    print("\nTry: the dashboard (spend by month/category/supplier), Duplicates,")
    print("Anomalies, semantic search ('toner HP'), the chat ('quanto abbiamo")
    print("speso in consulenza?'), and the Cost Saving Agent ('Trova opportunità")
    print("di risparmio').")


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


