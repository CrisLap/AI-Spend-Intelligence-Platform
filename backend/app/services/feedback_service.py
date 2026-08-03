from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document import Document, LineItem
from app.models.feedback import Feedback
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
    # Ownership checks: without these, any authenticated user could submit
    # feedback against another user's document_id/line_item_id and have
    # this function silently overwrite that line item's classification.
    document = db.query(Document).filter(Document.id == document_id, Document.user_id == user_id).first()
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
    # similarity, so it needs real text to be of any use.
    if item and item.description:
        classifier.seed_feedback_exemplars([(item.description, fb.corrected_category)])

    return fb


def get_feedback_for_training(db: Session, limit: int = 500) -> list[Feedback]:
    return db.query(Feedback).filter(
        Feedback.is_used_for_training == False  # noqa: E712
    ).limit(limit).all()


def mark_trained(db: Session, feedback_ids: list[int]) -> None:
    db.query(Feedback).filter(Feedback.id.in_(feedback_ids)).update(
        {"is_used_for_training": True}, synchronize_session=False
    )
    db.commit()
