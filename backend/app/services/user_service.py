from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import User
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.user_repository import UserRepository
from app.services.request_context import get_request_ip, get_request_user_agent


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.users = UserRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def list_users(self) -> list[User]:
        return self.users.list_all()

    def create_user(
        self,
        *,
        actor: User,
        email: str,
        username: str,
        password: str,
        request: Request,
    ) -> User:
        if self.users.get_by_email(email) is not None:
            raise ValueError("User with this email already exists")

        user = self.users.create(
            email=email,
            username=username,
            password_hash=hash_password(password),
            role="user",
            status="active",
            created_by_user_id=actor.id,
        )
        self.audit_logs.create(
            "create_user",
            actor_user_id=actor.id,
            target_type="user",
            target_id=str(user.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={"email": user.email},
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_status(
        self, *, actor: User, user_id: UUID, status: str, request: Request
    ) -> User:
        user = self._get_existing_user(user_id)
        user.status = status
        self.audit_logs.create(
            "enable_user" if status == "active" else "disable_user",
            actor_user_id=actor.id,
            target_type="user",
            target_id=str(user.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={"email": user.email, "status": status},
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def reset_password(
        self, *, actor: User, user_id: UUID, password: str, request: Request
    ) -> User:
        user = self._get_existing_user(user_id)
        user.password_hash = hash_password(password)
        self.audit_logs.create(
            "reset_password",
            actor_user_id=actor.id,
            target_type="user",
            target_id=str(user.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={"email": user.email},
        )
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete_user(self, *, actor: User, user_id: UUID, request: Request) -> None:
        user = self._get_existing_user(user_id)
        if user.id == actor.id:
            raise ValueError("Cannot delete your own account")
        if user.role == "admin" and self.users.count_by_role("admin") <= 1:
            raise ValueError("Cannot delete the last admin account")

        self.audit_logs.create(
            "delete_user",
            actor_user_id=actor.id,
            target_type="user",
            target_id=str(user.id),
            ip_address=get_request_ip(request),
            user_agent=get_request_user_agent(request),
            metadata={"email": user.email, "role": user.role},
        )
        self.users.delete(user)
        self.db.commit()

    def _get_existing_user(self, user_id: UUID) -> User:
        user = self.users.get_by_id(user_id)
        if user is None:
            raise ValueError("User not found")
        return user
