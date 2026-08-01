from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.document import LineItem
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
    original_method = None
    if line_item_id:
        item = db.query(LineItem).filter(LineItem.id == line_item_id).first()
        if item:
            original_category = original_category or item.category_label
            original_method = item.classification_method
            item.category_label = corrected_category
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

    classifier.seed_feedback_exemplars([(fb.original_category or "", fb.corrected_category)])

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
