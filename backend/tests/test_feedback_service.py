from __future__ import annotations

import pytest

from app.models.document import Document, LineItem
from app.models.user import User
from app.services import classifier
from app.services.feedback_service import save_feedback


def _make_user(db, email: str, role: str = "buyer") -> User:
    from app.core.security import hash_password
    u = User(email=email, hashed_password=hash_password("x"), full_name="U", role=role)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _make_document_with_item(db, owner: User, description: str = "Laptop Dell Precision workstation"):
    doc = Document(user_id=owner.id, filename="f.csv", original_name="f.csv", file_path="/tmp/f.csv")
    db.add(doc)
    db.commit()
    db.refresh(doc)
    item = LineItem(
        document_id=doc.id, description=description,
        category_label="Computer Equipment & Accessories", classification_method="rule_based",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return doc, item


def test_save_feedback_happy_path_seeds_exemplar_with_description(db):
    original = {c: list(v) for c, v in classifier._FEEDBACK_EXEMPLARS.items()}
    try:
        user = _make_user(db, "owner1@test.com")
        doc, item = _make_document_with_item(db, user)

        fb = save_feedback(
            db=db, user_id=user.id, document_id=doc.id, line_item_id=item.id,
            corrected_category="Professional & Consulting Services",
        )

        assert fb.corrected_category == "Professional & Consulting Services"
        db.refresh(item)
        assert item.category_label == "Professional & Consulting Services"
        assert item.classification_method == "feedback"
        # The exemplar seeded must be the real description text, not the
        # old category label. Keyed by (role, category) - see
        # classifier.py::_FEEDBACK_EXEMPLARS - the pool here is "buyer"
        # since both the acting user and the document owner are buyers.
        assert item.description in classifier._FEEDBACK_EXEMPLARS[("buyer", "Professional & Consulting Services")]
    finally:
        classifier._FEEDBACK_EXEMPLARS.clear()
        classifier._FEEDBACK_EXEMPLARS.update(original)


def test_save_feedback_rejects_document_owned_by_different_role(db):
    """Spend data is shared per role, not per user - a same-role teammate
    CAN give feedback on another user's document (see
    test_same_role_teammate_can_give_feedback_on_shared_document below);
    only a different role must still be rejected."""
    owner = _make_user(db, "owner2@test.com", role="buyer")
    outsider = _make_user(db, "outsider2@test.com", role="finance")
    doc, item = _make_document_with_item(db, owner)

    with pytest.raises(ValueError, match="not found"):
        save_feedback(
            db=db, user_id=outsider.id, document_id=doc.id, line_item_id=item.id,
            corrected_category="Professional & Consulting Services",
        )
    # The line item must be untouched.
    db.refresh(item)
    assert item.category_label == "Computer Equipment & Accessories"


def test_same_role_teammate_can_give_feedback_on_shared_document(db):
    owner = _make_user(db, "owner2b@test.com", role="buyer")
    teammate = _make_user(db, "teammate2b@test.com", role="buyer")
    doc, item = _make_document_with_item(db, owner)

    fb = save_feedback(
        db=db, user_id=teammate.id, document_id=doc.id, line_item_id=item.id,
        corrected_category="Professional & Consulting Services",
    )
    assert fb.corrected_category == "Professional & Consulting Services"
    db.refresh(item)
    assert item.category_label == "Professional & Consulting Services"


def test_save_feedback_rejects_line_item_from_a_different_document(db):
    owner = _make_user(db, "owner3@test.com")
    doc1, item1 = _make_document_with_item(db, owner, "Item in doc 1")
    doc2, _item2 = _make_document_with_item(db, owner, "Item in doc 2")

    with pytest.raises(ValueError, match="not found"):
        save_feedback(
            db=db, user_id=owner.id, document_id=doc2.id, line_item_id=item1.id,
            corrected_category="Professional & Consulting Services",
        )


def test_save_feedback_rejects_invalid_category(db):
    owner = _make_user(db, "owner4@test.com")
    doc, item = _make_document_with_item(db, owner)

    with pytest.raises(ValueError, match="must be one of"):
        save_feedback(
            db=db, user_id=owner.id, document_id=doc.id, line_item_id=item.id,
            corrected_category="Not A Real Category",
        )
