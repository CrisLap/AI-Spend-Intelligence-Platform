from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document import Document, LineItem
from app.models.feedback import Feedback
from app.models.user import User
from app.services import classifier


def save_feedback(
    db: Session,
    user_id: int,
    document_id: int,
    corrected_category: str,
    line_item_id: int | None = None,
    original_category: str | None = None,
    comment: str | None = None,
) -> Feedback:
    # Scope check: without this, any authenticated user could submit
    # feedback against a document outside their visible pool and have this
    # function silently overwrite that line item's classification. Mirrors
    # the same role-based scope used for reads elsewhere (get_visible_user_ids),
    # recomputed here since this function only receives a raw user_id.
    requester = db.query(User).filter(User.id == user_id).first()
    doc_query = db.query(Document).filter(Document.id == document_id)
    if requester is not None and requester.role != "admin":
        visible_ids = [r[0] for r in db.query(User.id).filter(User.role == requester.role).all()]
        doc_query = doc_query.filter(Document.user_id.in_(visible_ids))
    document = doc_query.first()
    if not document:
        raise ValueError("Document not found")

    if corrected_category not in classifier.UNSPSC_TAXONOMY:
        raise ValueError(f"corrected_category must be one of {sorted(classifier.UNSPSC_TAXONOMY)}")

    original_method = None
    item = None
    if line_item_id:
        item = db.query(LineItem).filter(
            LineItem.id == line_item_id, LineItem.document_id == document_id
        ).first()
        if not item:
            raise ValueError("Line item not found for this document")
        original_category = original_category or item.category_label
        original_method = item.classification_method
        item.category_label = corrected_category
        item.classification_method = "feedback"

    fb = Feedback(
        user_id=user_id,
        document_id=document_id,
        line_item_id=line_item_id,
        original_category=original_category,
        corrected_category=corrected_category,
        original_method=original_method,
        comment=comment,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)

    # Feed the actual description text, not the category label - the
    # classifier compares this against future descriptions via embedding
    # similarity, so it needs real text to be of any use. Scoped to the
    # document's own owner role (the pool it belongs to), not necessarily
    # the correcting user's role (relevant when an admin corrects a
    # buyer/finance document).
    if item and item.description:
        owner = requester if document.user_id == user_id else db.query(User).filter(User.id == document.user_id).first()
        owner_role = owner.role if owner else "buyer"
        classifier.seed_feedback_exemplars([(item.description, fb.corrected_category, owner_role)])

    return fb


def get_feedback_for_training(db: Session, limit: int = 500, user_ids: list[int] | None = None) -> list[Feedback]:
    query = db.query(Feedback).filter(Feedback.is_used_for_training == False)  # noqa: E712
    if user_ids is not None:
        query = (
            query.join(Document, Feedback.document_id == Document.id)
            .filter(Document.user_id.in_(user_ids))
        )
    return query.limit(limit).all()


def mark_trained(db: Session, feedback_ids: list[int]) -> None:
    db.query(Feedback).filter(Feedback.id.in_(feedback_ids)).update(
        {"is_used_for_training": True}, synchronize_session=False
    )
    db.commit()
