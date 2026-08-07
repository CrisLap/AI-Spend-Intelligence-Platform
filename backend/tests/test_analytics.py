from __future__ import annotations

from app.core.security import hash_password
from app.models.document import Document, LineItem
from app.models.user import User
from app.services.analytics import get_dashboard


def _make_user(db, email: str, user_id: int | None = None) -> User:
    if user_id is not None:
        existing = db.query(User).filter(User.id == user_id).first()
        if existing:
            return existing
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role="buyer")
    if user_id is not None:
        u.id = user_id
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_item(db, owner: User, total: float) -> None:
    doc = Document(user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    db.add(LineItem(document_id=doc.id, description="item", total=total))
    db.commit()


def test_dashboard_isolates_by_user_even_when_user_id_is_zero(db):
    """user_id=0 must not be treated as 'no filter' - it's a valid id and
    the old `if user_id:` check silently returned every user's spend.
    No document/line item is ever owned by user_id=0 here, so the fixed
    behavior must show zero spend, not the other user's 5000.0."""
    other = _make_user(db, "dashother@test.com")
    _make_item(db, other, 5000.0)

    dashboard = get_dashboard(user_id=0, db=db)

    assert dashboard["total_spend"] == 0.0


def test_dashboard_endpoint_works_without_a_real_postgres_running(client, auth_headers):
    """get_dashboard used to always open its own SessionLocal() bound to
    settings.database_url (real Postgres), ignoring the test override -
    this endpoint would only work if a real Postgres server were reachable."""
    r = client.get("/analytics/dashboard", headers=auth_headers)
    assert r.status_code == 200