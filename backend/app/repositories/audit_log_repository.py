from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import AuditLog


class AuditLogRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        action: str,
        *,
        actor_user_id: UUID | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        log = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            ip_address=ip_address,
            user_agent=user_agent,
            audit_metadata=metadata,
        )
        self.db.add(log)
        self.db.flush()
        return log

