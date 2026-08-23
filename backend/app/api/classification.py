from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.rate_limit import limiter
from app.models.document import Document, LineItem
from app.models.user import User
from app.schemas.document import LineItemOut, LineItemUpdate
from app.services.audit_service import log_action
from app.services.classifier import classify_batch, classify_description, seed_feedback_exemplars
from app.services.feedback_service import get_feedback_for_training, mark_trained

router = APIRouter(prefix="/classification", tags=["classification"], dependencies=[Depends(get_current_user)])


class ClassifyRequest(BaseModel):
    descriptions: Annotated[list[Annotated[str, Field(max_length=500)]], Field(max_length=200)]


class ClassifyResponse(BaseModel):
    results: list[dict]


class ClassifySingleRequest(BaseModel):
    desc: str = Field(..., min_length=1, max_length=2000)


@router.post("", response_model=ClassifyResponse)
@limiter.limit("20/minute")
def classify(request: Request, payload: ClassifyRequest, user: User = Depends(get_current_user)):
    return ClassifyResponse(results=classify_batch(payload.descriptions))


@router.post("/single", response_model=dict)
@limiter.limit("20/minute")
def classify_single(request: Request, payload: ClassifySingleRequest, user: User = Depends(get_current_user)):
    return classify_description(payload.desc)


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

    line_item_ids = [fb.line_item_id for fb in feedbacks if fb.line_item_id]
    items_by_id = {}
    if line_item_ids:
        items = db.query(LineItem).filter(LineItem.id.in_(line_item_ids)).all()
        items_by_id = {i.id: i for i in items}

    pairs = [
        (items_by_id[fb.line_item_id].description, fb.corrected_category)
        for fb in feedbacks
        if fb.line_item_id in items_by_id and items_by_id[fb.line_item_id].description
    ]
    seed_feedback_exemplars(pairs)
    mark_trained(db, [fb.id for fb in feedbacks])
    log_action(
        db,
        user_id=user.id,
        action="retrain_classifier",
        entity_type="classifier",
        details={"feedback_count": len(feedbacks), "exemplars_added": len(pairs)},
    )
    return {
        "trained": len(feedbacks),
        "message": f"Classifier updated with {len(pairs)} of {len(feedbacks)} feedback corrections "
        "(some entries had no linked line item or description and were skipped)"
        if len(pairs) < len(feedbacks)
        else f"Classifier updated with {len(pairs)} feedback corrections",
    }