from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_visible_user_ids
from app.models.document import Document, LineItem, LineItemGroup, LineItemGroupItem
from app.models.user import User
from app.schemas.document import ResolvedUpdate
from app.services.audit_service import log_action

router = APIRouter(prefix="/duplicates", tags=["duplicates"], dependencies=[Depends(get_current_user)])


def _own_group_ids_query(db: Session, user: User, search: str | None = None):
    q = (
        db.query(LineItemGroupItem.group_id)
        .join(LineItem, LineItemGroupItem.line_item_id == LineItem.id)
        .join(Document, LineItem.document_id == Document.id)
    )
    scope = get_visible_user_ids(user, db)
    if scope is not None:
        q = q.filter(Document.user_id.in_(scope))
    if search:
        like = f"%{search}%"
        q = q.filter(or_(LineItem.description.ilike(like), LineItem.supplier.ilike(like)))
    return q.distinct()


@router.get("")
def list_duplicates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=200),
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only groups that contain at least one line item within the current
    # user's visible scope (their own role's pool, or everything for admin).
    own_group_ids = _own_group_ids_query(db, user, search)
    query = db.query(LineItemGroup).filter(LineItemGroup.id.in_(own_group_ids))
    if not include_resolved:
        query = query.filter(LineItemGroup.resolved == False)  # noqa: E712
    groups = query.order_by(LineItemGroup.created_at.desc()).offset(skip).limit(limit).all()
    scope = get_visible_user_ids(user, db)
    group_ids = [g.id for g in groups]

    # Two batched queries for the whole page instead of one query per group
    # plus one query per item in that group (previously N+1).
    links = (
        db.query(LineItemGroupItem).filter(LineItemGroupItem.group_id.in_(group_ids)).all()
        if group_ids else []
    )
    links_by_group: dict[int, list[int]] = {}
    for link in links:
        links_by_group.setdefault(link.group_id, []).append(link.line_item_id)

    line_item_ids = [link.line_item_id for link in links]
    items_by_id: dict[int, LineItem] = {}
    if line_item_ids:
        item_query = (
            db.query(LineItem)
            .join(Document, LineItem.document_id == Document.id)
            .filter(LineItem.id.in_(line_item_ids))
        )
        if scope is not None:
            item_query = item_query.filter(Document.user_id.in_(scope))
        items_by_id = {item.id: item for item in item_query.all()}

    result = []
    for g in groups:
        group_items = []
        for line_item_id in links_by_group.get(g.id, []):
            item = items_by_id.get(line_item_id)
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
            "resolved": g.resolved,
        })
    return result


@router.patch("/{group_id}/resolve")
def resolve_duplicate(
    group_id: int,
    body: ResolvedUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    own_group_ids = _own_group_ids_query(db, user)
    group = db.query(LineItemGroup).filter(
        LineItemGroup.id == group_id,
        LineItemGroup.id.in_(own_group_ids),
    ).first()
    if not group:
        raise HTTPException(status_code=404, detail="Duplicate group not found")
    group.resolved = body.resolved
    db.commit()
    log_action(
        db, user_id=user.id,
        action="resolve_duplicate" if body.resolved else "unresolve_duplicate",
        entity_type="line_item_group", entity_id=group.id,
        details={"resolved": body.resolved},
    )
    return {"id": group.id, "resolved": group.resolved}
