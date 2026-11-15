"""Deterministic spend dataset for the agent-answer evaluation suite
(run_eval.py). Every number an eval question checks is derived from this
exact dataset, either via a raw SQL query or via the same deterministic
service function the app itself uses (analytics.py) - see questions.yaml.

Deliberately NOT a reuse of scripts/seed_demo_data.py: that script targets
whatever DATABASE_URL/Postgres instance is configured, which the eval
harness has no business depending on (CI has no Postgres service
container). This builds its own isolated SQLite database instead - see
run_eval.py, which sets DATABASE_URL to a temp SQLite file before
importing anything from `app`, so the whole app (including
chat_service.answer_question and cost_saving_agent.analyze, which open
their own SessionLocal()) transparently reads/writes that file.
"""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.document import ContractClause, DocType, Document, DocumentStatus, LineItem
from app.models.user import User

EVAL_BUYER_EMAIL = "eval.buyer@spend.local"

# Renewal/penalty language is in Italian AND English on purpose: whichever
# embedding path ends up active (Ollama, Jina, or the offline deterministic
# hash fallback - see app/services/ai.py), the contract_risk agent's search
# queries (cost_saving_agent.py's _RENEWAL_SEARCH_QUERIES/_RISK_SEARCH_QUERIES,
# a mix of Italian and English phrases) have literal token overlap with this
# text, so the match doesn't depend on a real embedding provider being
# reachable in whatever environment runs this eval.
_CONTRACT_RAW_TEXT = (
    "Clause 1 - Payment terms.\n\n"
    "Payments are due within 30 days of invoice.\n\n"
    "Clause 2 - Renewal and termination.\n\n"
    "This agreement includes a rinnovo automatico tacito (automatic renewal "
    "clause) unless terminated with 90 days notice, and a penale per recesso "
    "anticipato (early termination penalty) equal to 10% of the remaining "
    "contract value.\n\n"
    "Clause 3 - Liability.\n\n"
    "Standard liability terms apply, capped at the total contract value."
)

# (supplier, category, month, total) - each supplier has exactly 4 line
# items across 4 months so get_supplier_variance (min_items=4) computes a
# variance for every one of them; Acme Corp's sharp mid-period jump makes
# it the unambiguous "biggest increase" answer.
_ROWS = [
    ("Acme Corp", "IT Services", 1, 1000.00),
    ("Global Logistics", "Logistics", 1, 500.00),
    ("Office Depot", "Office Supplies", 1, 150.00),
    ("CloudHost Inc", "Cloud Hosting", 1, 290.00),
    ("Acme Corp", "IT Services", 2, 1000.00),
    ("Global Logistics", "Logistics", 2, 520.00),
    ("Office Depot", "Office Supplies", 2, 140.00),
    ("CloudHost Inc", "Cloud Hosting", 2, 300.00),
    ("Acme Corp", "IT Services", 3, 1800.00),
    ("Global Logistics", "Logistics", 3, 510.00),
    ("Office Depot", "Office Supplies", 3, 160.00),
    ("CloudHost Inc", "Cloud Hosting", 3, 320.00),
    ("Acme Corp", "IT Services", 4, 1900.00),
    ("Global Logistics", "Logistics", 4, 490.00),
    ("Office Depot", "Office Supplies", 4, 155.00),
    ("CloudHost Inc", "Cloud Hosting", 4, 310.00),
]


def _dt(month: int, day: int = 15) -> datetime:
    return datetime(2025, month, day, tzinfo=UTC)


def seed(db: Session) -> dict:
    """Populates the given (empty, already-migrated) session with the
    fixed eval dataset. Returns {"buyer_id": int} - the acting user for
    every question in questions.yaml."""
    buyer = User(
        email=EVAL_BUYER_EMAIL,
        hashed_password=hash_password("eval-not-a-real-password"),
        full_name="Eval Buyer",
        role="buyer",
    )
    db.add(buyer)
    db.commit()
    db.refresh(buyer)

    invoices_doc = Document(
        user_id=buyer.id, filename="eval_invoices.csv", original_name="eval_invoices.csv",
        doc_type=DocType.invoice, status=DocumentStatus.classified,
    )
    db.add(invoices_doc)
    db.commit()
    db.refresh(invoices_doc)

    for supplier, category, month, total in _ROWS:
        db.add(LineItem(
            document_id=invoices_doc.id,
            description=f"{category} - {supplier}",
            quantity=1.0, unit_price=total, total=total,
            supplier=supplier, category_label=category,
            created_at=_dt(month),
        ))
    db.commit()

    # The dataset's single anomalous/highest-value item - is_anomaly is set
    # directly (same "persisted once at processing time" convention
    # list_anomalies_for reads), not recomputed by detect_anomalies(), to
    # keep this fixture independent of the z-score threshold setting.
    db.add(LineItem(
        document_id=invoices_doc.id,
        description="Emergency hardware replacement - NewVendor LLC",
        quantity=1.0, unit_price=2500.00, total=2500.00,
        supplier="NewVendor LLC", category_label="Hardware",
        is_anomaly=True, anomaly_score=4.2,
        anomaly_reason="Price 2500.00 deviates sharply from category peers",
        created_at=_dt(4, day=20),
    ))
    db.commit()

    contract_doc = Document(
        user_id=buyer.id, filename="eval_contract.pdf", original_name="eval_contract.pdf",
        doc_type=DocType.contract, status=DocumentStatus.classified, raw_text=_CONTRACT_RAW_TEXT,
    )
    db.add(contract_doc)
    db.commit()
    db.refresh(contract_doc)

    for idx, chunk in enumerate(p for p in _CONTRACT_RAW_TEXT.split("\n\n") if p.strip()):
        db.add(ContractClause(document_id=contract_doc.id, chunk_index=idx, text=chunk.strip()))
    db.commit()

    return {"buyer_id": buyer.id}
