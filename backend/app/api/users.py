from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.audit import AuditLog
from app.models.user import User
from app.schemas.user import RoleUpdate, UserOut
from app.services.audit_service import log_action

VALID_ROLES = {"admin", "buyer", "finance"}

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    return [UserOut.model_validate(u) for u in db.query(User).order_by(User.created_at).all()]


@router.patch("/{user_id}/role", response_model=UserOut)
def update_user_role(
    user_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if payload.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {sorted(VALID_ROLES)}")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    previous_role = user.role
    user.role = payload.role
    db.commit()
    db.refresh(user)
    log_action(
        db,
        user_id=admin.id,
        action="update_role",
        entity_type="user",
        entity_id=user.id,
        details={"previous_role": previous_role, "new_role": payload.role},
    )
    return UserOut.model_validate(user)


@router.get("/{user_id}/audit-log")
def get_user_audit_log(
    user_id: int,
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_role("admin")),
):
    entries = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": e.id,
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "details": e.details,
            "created_at": e.created_at,
        }
        for e in entries
    ]

