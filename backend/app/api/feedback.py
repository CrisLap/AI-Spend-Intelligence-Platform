from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.feedback import FeedbackCreate, FeedbackOut
from app.services.audit_service import log_action
from app.services.feedback_service import save_feedback

router = APIRouter(prefix="/feedback", tags=["feedback"], dependencies=[Depends(get_current_user)])


@router.post("", response_model=FeedbackOut, status_code=201)
def create_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        fb = save_feedback(
            db=db,
            user_id=user.id,
            document_id=payload.document_id,
            line_item_id=payload.line_item_id,
            original_category=payload.original_category,
            corrected_category=payload.corrected_category,
            comment=payload.comment,
        )
    except ValueError as e:
        status = 404 if "not found" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e)) from e
    log_action(
        db, user_id=user.id, action="submit_feedback", entity_type="line_item",
        entity_id=payload.line_item_id,
        details={"original_category": payload.original_category, "corrected_category": payload.corrected_category},
    )
    return FeedbackOut.model_validate(fb)

