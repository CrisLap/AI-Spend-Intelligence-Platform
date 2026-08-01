from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models.audit import AuditLog
from app.models.chat import ChatMessage, ChatSession
from app.models.document import Document, LineItem, LineItemGroup, LineItemGroupItem
from app.models.feedback import Feedback
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


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    deleted_email = user.email

    docs = db.query(Document).filter(Document.user_id == user_id).all()
    doc_ids = [d.id for d in docs]
    for d in docs:
        try:
            Path(d.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    item_ids = [i.id for i in db.query(LineItem.id).filter(LineItem.document_id.in_(doc_ids)).all()]
    group_ids = [
        g.group_id
        for g in db.query(LineItemGroupItem.group_id).filter(LineItemGroupItem.line_item_id.in_(item_ids)).distinct()
    ]
    session_ids = [s.id for s in db.query(ChatSession.id).filter(ChatSession.user_id == user_id).all()]

    # Delete in dependency order (children before parents), mirroring the
    # same cascade used by scripts/seed_demo_data.py's wipe_demo_data, so
    # this works against real foreign key constraints (Postgres/Neon).
    db.query(ChatMessage).filter(ChatMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
    db.query(ChatSession).filter(ChatSession.id.in_(session_ids)).delete(synchronize_session=False)
    db.query(Feedback).filter(
        (Feedback.user_id == user_id) | (Feedback.document_id.in_(doc_ids))
    ).delete(synchronize_session=False)
    db.query(LineItemGroupItem).filter(LineItemGroupItem.line_item_id.in_(item_ids)).delete(synchronize_session=False)
    db.query(LineItemGroup).filter(LineItemGroup.id.in_(group_ids)).delete(synchronize_session=False)
    db.query(LineItem).filter(LineItem.document_id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.id.in_(doc_ids)).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.user_id == user_id).delete(synchronize_session=False)
    db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
    db.commit()

    log_action(
        db,
        user_id=admin.id,
        action="delete_user",
        entity_type="user",
        entity_id=user_id,
        details={"deleted_email": deleted_email, "documents_deleted": len(doc_ids)},
    )
    return {"deleted": True, "user_id": user_id, "email": deleted_email, "documents_deleted": len(doc_ids)}

