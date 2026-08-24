from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.document import Document, LineItem
from app.models.user import User
from app.schemas.document import ResolvedUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/anomalies", tags=["anomalies"], dependencies=[Depends(get_current_user)])

_SORT_COLUMNS = {
    "zscore": LineItem.anomaly_score,
    "price": LineItem.unit_price,
}


@router.get("")
def list_anomalies(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=200),
    sort_by: Literal["zscore", "price"] = "zscore",
    sort_dir: Literal["asc", "desc"] = "desc",
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(LineItem).join(Document).filter(
        Document.user_id == user.id,
        LineItem.is_anomaly == True,  # noqa: E712
    )
    if not include_resolved:
        query = query.filter(LineItem.anomaly_resolved == False)  # noqa: E712
    if search:
        like = f"%{search}%"
        query = query.filter(or_(
            LineItem.description.ilike(like),
            LineItem.supplier.ilike(like),
            LineItem.category_label.ilike(like),
        ))
    column = _SORT_COLUMNS[sort_by]
    order = column.asc() if sort_dir == "asc" else column.desc()
    items = query.order_by(order).offset(skip).limit(limit).all()
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
            "resolved": i.anomaly_resolved,
        }
        for i in items
    ]


@router.patch("/{line_item_id}/resolve")
def resolve_anomaly(
    line_item_id: int,
    body: ResolvedUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = db.query(LineItem).join(Document).filter(
        LineItem.id == line_item_id,
        Document.user_id == user.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    item.anomaly_resolved = body.resolved
    db.commit()
    log_action(
        db, user_id=user.id,
        action="resolve_anomaly" if body.resolved else "unresolve_anomaly",
        entity_type="line_item", entity_id=item.id,
        details={"resolved": body.resolved},
    )
    return {"id": item.id, "resolved": item.anomaly_resolved}
