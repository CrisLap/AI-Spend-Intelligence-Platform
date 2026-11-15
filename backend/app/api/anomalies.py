from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_visible_user_ids
from app.models.document import Document, LineItem
from app.models.user import User
from app.schemas.document import ResolvedUpdate
from app.services.anomalies import list_anomalies_for
from app.services.audit_service import log_action

router = APIRouter(prefix="/anomalies", tags=["anomalies"], dependencies=[Depends(get_current_user)])


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
    scope = get_visible_user_ids(user, db)
    return list_anomalies_for(
        db, scope, skip=skip, limit=limit, search=search,
        sort_by=sort_by, sort_dir=sort_dir, include_resolved=include_resolved,
    )


@router.patch("/{line_item_id}/resolve")
def resolve_anomaly(
    line_item_id: int,
    body: ResolvedUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scope = get_visible_user_ids(user, db)
    query = db.query(LineItem).join(Document).filter(LineItem.id == line_item_id)
    if scope is not None:
        query = query.filter(Document.user_id.in_(scope))
    item = query.first()
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
