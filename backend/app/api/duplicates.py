from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_visible_user_ids
from app.models.document import LineItemGroup
from app.models.user import User
from app.schemas.document import ResolvedUpdate
from app.services.audit_service import log_action
from app.services.duplicates import list_duplicates_for, visible_group_ids

router = APIRouter(prefix="/duplicates", tags=["duplicates"], dependencies=[Depends(get_current_user)])


@router.get("")
def list_duplicates(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=200),
    include_resolved: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scope = get_visible_user_ids(user, db)
    return list_duplicates_for(db, scope, skip=skip, limit=limit, search=search, include_resolved=include_resolved)


@router.patch("/{group_id}/resolve")
def resolve_duplicate(
    group_id: int,
    body: ResolvedUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scope = get_visible_user_ids(user, db)
    own_group_ids = visible_group_ids(db, scope)
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
