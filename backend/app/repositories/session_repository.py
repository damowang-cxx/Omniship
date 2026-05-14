from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import UserSession


class UserSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: UUID,
        session_token_hash: str,
        expires_at: datetime,
    ) -> UserSession:
        session = UserSession(
            user_id=user_id,
            session_token_hash=session_token_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def get_active_by_token_hash(self, session_token_hash: str) -> UserSession | None:
        now = datetime.now(timezone.utc)
        statement = (
            select(UserSession)
            .options(joinedload(UserSession.user))
            .where(
                UserSession.session_token_hash == session_token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
        )
        return self.db.execute(statement).scalar_one_or_none()

    def revoke_by_token_hash(self, session_token_hash: str) -> UserSession | None:
        session = self.get_active_by_token_hash(session_token_hash)
        if session is None:
            return None
        session.revoked_at = datetime.now(timezone.utc)
        self.db.flush()
        return session

