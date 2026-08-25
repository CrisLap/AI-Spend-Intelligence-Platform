from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_visible_user_ids
from app.models.user import User
from app.services.search import semantic_search

router = APIRouter(prefix="/search", tags=["search"], dependencies=[Depends(get_current_user)])


@router.get("")
def search(
    q: str = Query(..., description="Natural language search query"),
    top_k: int = Query(10, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    results = semantic_search(q, top_k=top_k, user_id=get_visible_user_ids(user, db), db=db)
    return {"query": q, "total": len(results), "results": results}
