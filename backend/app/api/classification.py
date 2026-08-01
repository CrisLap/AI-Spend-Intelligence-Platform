from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.models.document import Document, LineItem
from app.models.user import User
from app.schemas.document import LineItemOut, LineItemUpdate
from app.services.audit_service import log_action
from app.services.classifier import classify_batch, classify_description, seed_feedback_exemplars
from app.services.feedback_service import get_feedback_for_training, mark_trained

router = APIRouter(prefix="/classification", tags=["classification"])


class ClassifyRequest(BaseModel):
    descriptions: list[str]


class ClassifyResponse(BaseModel):
    results: list[dict]


@router.post("", response_model=ClassifyResponse)
def classify(payload: ClassifyRequest, user: User = Depends(get_current_user)):
    return ClassifyResponse(results=classify_batch(payload.descriptions))


@router.post("/single", response_model=dict)
def classify_single(desc: str, user: User = Depends(get_current_user)):
    return classify_description(desc)


@router.patch("/line-items/{item_id}", response_model=LineItemOut)
def update_line_item(
    item_id: int,
    payload: LineItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = (
        db.query(LineItem)
        .join(Document, LineItem.document_id == Document.id)
        .filter(LineItem.id == item_id, Document.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Line item not found")
    old_cat = item.category_label
    if payload.category_label is not None:
        item.category_label = payload.category_label
        if old_cat and old_cat != payload.category_label:
            seed_feedback_exemplars([(item.description, payload.category_label)])
    if payload.category_unspsc is not None:
        item.category_unspsc = payload.category_unspsc
    if payload.supplier is not None:
        item.supplier = payload.supplier
    if payload.description is not None:
        item.description = payload.description
    db.commit()
    db.refresh(item)
    log_action(
        db,
        user_id=user.id,
        action="correct_classification",
        entity_type="line_item",
        entity_id=item.id,
        details={"previous_category": old_cat, "new_category": item.category_label},
    )
    return LineItemOut.model_validate(item)


@router.post("/retrain")
def retrain_from_feedback(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin", "finance")),
):
    feedbacks = get_feedback_for_training(db)
    if not feedbacks:
        return {"trained": 0, "message": "No new feedback to train on"}
    pairs = [(fb.original_category or "", fb.corrected_category) for fb in feedbacks]
    seed_feedback_exemplars(pairs)
    mark_trained(db, [fb.id for fb in feedbacks])
    log_action(
        db,
        user_id=user.id,
        action="retrain_classifier",
        entity_type="classifier",
        details={"feedback_count": len(pairs)},
    )
    return {"trained": len(pairs), "message": f"Classifier updated with {len(pairs)} feedback corrections"}
