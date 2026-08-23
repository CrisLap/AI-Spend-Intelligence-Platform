from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.document import Document, LineItem, LineItemGroup, LineItemGroupItem
from app.models.user import User

router = APIRouter(prefix="/duplicates", tags=["duplicates"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_duplicates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only groups that contain at least one line item belonging to the
    # current user's own documents (previously this returned every user's
    # duplicate groups, regardless of ownership).
    own_group_ids = (
        db.query(LineItemGroupItem.group_id)
        .join(LineItem, LineItemGroupItem.line_item_id == LineItem.id)
        .join(Document, LineItem.document_id == Document.id)
        .filter(Document.user_id == user.id)
        .distinct()
    )
    groups = (
        db.query(LineItemGroup)
        .filter(LineItemGroup.id.in_(own_group_ids))
        .order_by(LineItemGroup.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    result = []
    for g in groups:
        group_item_links = db.query(LineItemGroupItem).filter(
            LineItemGroupItem.group_id == g.id
        ).all()
        group_items = []
        for gi in group_item_links:
            item = (
                db.query(LineItem)
                .join(Document, LineItem.document_id == Document.id)
                .filter(LineItem.id == gi.line_item_id, Document.user_id == user.id)
                .first()
            )
            if item:
                group_items.append({
                    "id": item.id,
                    "description": item.description,
                    "supplier": item.supplier,
                    "total": item.total,
                    "invoice_number": item.invoice_number,
                })
        result.append({
            "id": g.id,
            "reason": g.reason,
            "similarity": g.similarity,
            "items": group_items,
        })
    return result
