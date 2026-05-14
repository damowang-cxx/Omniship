from datetime import datetime, timezone

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_session_token
from app.db.models import User
from app.db.session import get_db
from app.repositories.session_repository import UserSessionRepository


def get_current_user(
    db: Session = Depends(get_db),
    session_token: str | None = Cookie(default=None, alias="integrer_session"),
) -> User:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    session = UserSessionRepository(db).get_active_by_token_hash(
        hash_session_token(session_token)
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    if session.user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is disabled",
        )

    session.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return session.user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permission required",
        )
    return current_user


def get_auth_cookie_name() -> str:
    return get_settings().auth_cookie_name

