from __future__ import annotations

import datetime as dt

from app.core.security import hash_password
from app.models.document import DocType, Document, LineItem
from app.models.user import User
from app.services.analytics import forecast_next_month_spend


def _make_user(db, email: str) -> User:
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_item(db, owner: User, total: float, created_at, doc_type=DocType.invoice) -> None:
    doc = Document(
        user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv", doc_type=doc_type
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.add(LineItem(document_id=doc.id, description="item", total=total, created_at=created_at))
    db.commit()


def test_forecast_unavailable_with_too_little_history(db):
    owner = _make_user(db, "forecastfew@test.com")
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    _make_item(db, owner, 100.0, base)
    _make_item(db, owner, 120.0, base + dt.timedelta(days=31))

    result = forecast_next_month_spend(user_id=owner.id, db=db)

    assert result["available"] is False


def test_forecast_projects_a_clear_upward_trend(db):
    """Deterministic check: four months increasing by exactly €100 each
    should fit a trend of ~€100/month and forecast ~€500 for the next
    month - not just "some number", a number that follows from the input."""
    owner = _make_user(db, "forecasttrend@test.com")
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    for i, total in enumerate([100.0, 200.0, 300.0, 400.0]):
        _make_item(db, owner, total, base + dt.timedelta(days=31 * i))

    result = forecast_next_month_spend(user_id=owner.id, db=db)

    assert result["available"] is True
    assert result["monthly_totals"] == [100.0, 200.0, 300.0, 400.0]
    assert result["trend_per_month"] == 100.0
    assert result["forecast_next_month"] == 500.0


def test_forecast_excludes_contract_line_items(db):
    """A contract's line item is typically a one-time face-value total, not
    a recurring monthly charge - mixing it in would distort the trend, same
    rationale as get_supplier_variance()'s contract exclusion."""
    owner = _make_user(db, "forecastcontract@test.com")
    base = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
    for i, total in enumerate([100.0, 200.0, 300.0]):
        _make_item(db, owner, total, base + dt.timedelta(days=31 * i))
    _make_item(db, owner, 50000.0, base, doc_type=DocType.contract)

    result = forecast_next_month_spend(user_id=owner.id, db=db)

    assert result["available"] is True
    assert result["monthly_totals"] == [100.0, 200.0, 300.0]
