from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        email: str,
        username: str,
        password_hash: str,
        role: str = "user",
        status: str = "active",
        created_by_user_id: UUID | None = None,
    ) -> User:
        user = User(
            email=email.lower().strip(),
            username=username.strip(),
            password_hash=password_hash,
            role=role,
            status=status,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(user)
        self.db.flush()
        return user

    def get_by_id(self, user_id: UUID) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(User.email == email.lower().strip())
        return self.db.execute(statement).scalar_one_or_none()

    def list_all(self) -> list[User]:
        statement = select(User).order_by(User.created_at.desc(), User.email.asc())
        return list(self.db.execute(statement).scalars().all())

