from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.document import Document, LineItem
from app.models.user import User

router = APIRouter(prefix="/anomalies", tags=["anomalies"])


@router.get("")
def list_anomalies(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items = db.query(LineItem).join(Document).filter(
        Document.user_id == user.id,
        LineItem.is_anomaly == True,  # noqa: E712
    ).order_by(LineItem.anomaly_score.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": i.id,
            "description": i.description,
            "unit_price": i.unit_price,
            "category": i.category_label,
            "supplier": i.supplier,
            "zscore": i.anomaly_score,
            "reason": i.anomaly_reason,
            "document_id": i.document_id,
        }
        for i in items
    ]
