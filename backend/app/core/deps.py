from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.services.i18n_strings import DEFAULT_LANG, SUPPORTED_LANGUAGES

_bearer = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == int(payload["sub"])).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
    return user


def require_role(*roles: str):
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
        return user
    return checker


def get_ui_language(x_ui_language: str | None = Header(default=None, alias="X-UI-Language")) -> str:
    """The frontend's currently-selected UI language (see frontend/src/api.ts,
    which sends this on every request), used to steer LLM output language and
    the language of deterministic backend-generated text (recommendations,
    guardrail messages, anomaly/duplicate reasons). Falls back to English for
    missing/unrecognized values instead of erroring, since this only affects
    which language generated text comes back in, never whether a request
    succeeds."""
    return x_ui_language if x_ui_language in SUPPORTED_LANGUAGES else DEFAULT_LANG
