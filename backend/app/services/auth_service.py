from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)
from app.db.models import User, UserSession
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.session_repository import UserSessionRepository
from app.repositories.user_repository import UserRepository
from app.services.request_context import get_request_ip, get_request_user_agent


class AuthError(ValueError):
    pass


class AuthService:
    def __init__(self, db: Session, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.users = UserRepository(db)
        self.sessions = UserSessionRepository(db)
        self.audit_logs = AuditLogRepository(db)

    def login(self, email: str, password: str, request: Request) -> tuple[User, str]:
        self.db.info.pop("impersonation", None)
        user = self.users.get_by_email(email)
        ip_address = get_request_ip(request)
        user_agent = get_request_user_agent(request)

        if (
            user is None
            or user.status != "active"
            or not verify_password(password, user.password_hash)
        ):
            self.audit_logs.create(
                "login_failed",
                ip_address=ip_address,
                user_agent=user_agent,
                metadata={"email": email.lower().strip()},
            )
            self.db.commit()
            raise AuthError("Invalid email or password")

        raw_token = generate_session_token()
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=self.settings.auth_session_ttl_hours
        )
        self.sessions.create(
            user_id=user.id,
            session_token_hash=hash_session_token(raw_token),
            expires_at=expires_at,
        )
        user.last_login_at = datetime.now(timezone.utc)
        self.audit_logs.create(
            "login_success",
            actor_user_id=user.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.commit()
        self.db.refresh(user)
        return user, raw_token

    def start_impersonation(self, session: UserSession, user_id: UUID, request: Request) -> User:
        if session.user.role != "admin" or session.impersonated_user_id is not None:
            raise PermissionError("Admin permission required")
        target = self.users.get_by_id(user_id)
        if target is None:
            raise AuthError("Customer not found")
        if target.role != "user" or target.status != "active":
            raise AuthError("Only active customer accounts can be entered")
        session.impersonated_user_id = target.id
        session.impersonated_user = target
        self.audit_logs.create(
            "start_impersonation", actor_user_id=session.user_id,
            target_type="user", target_id=str(target.id),
            ip_address=get_request_ip(request), user_agent=get_request_user_agent(request),
            metadata={"sessionId": str(session.id)},
        )
        self.db.commit()
        return target

    def stop_impersonation(self, session: UserSession, request: Request) -> User:
        if session.user.role != "admin":
            raise PermissionError("Admin permission required")
        if session.impersonated_user_id is not None:
            self.audit_logs.create(
                "stop_impersonation", actor_user_id=session.user_id,
                target_type="user", target_id=str(session.impersonated_user_id),
                ip_address=get_request_ip(request), user_agent=get_request_user_agent(request),
                metadata={"sessionId": str(session.id)},
            )
            session.impersonated_user_id = None
            session.impersonated_user = None
            self.db.commit()
        return session.user

    def logout(self, token: str | None, request: Request) -> None:
        if not token:
            return

        session = self.sessions.revoke_by_token_hash(hash_session_token(token))
        if session:
            self.audit_logs.create(
                "logout",
                actor_user_id=session.user_id,
                ip_address=get_request_ip(request),
                user_agent=get_request_user_agent(request),
            )
            self.db.commit()


def create_admin_user(db: Session, *, email: str, username: str, password: str) -> User:
    users = UserRepository(db)
    if users.get_by_email(email) is not None:
        raise ValueError("User with this email already exists")

    user = users.create(
        email=email,
        username=username,
        password_hash=hash_password(password),
        role="admin",
        status="active",
    )
    AuditLogRepository(db).create(
        "create_initial_admin",
        target_type="user",
        target_id=str(user.id),
        metadata={"email": user.email},
    )
    db.commit()
    db.refresh(user)
    return user

