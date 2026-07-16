from sqlalchemy.orm import Session
from decimal import Decimal

from app.core.security import hash_password
from app.repositories.user_repository import UserRepository


def create_test_user(
    db_session: Session,
    *,
    email: str,
    username: str = "Test User",
    password: str = "password123",
    role: str = "user",
    status: str = "active",
    balance: Decimal | str = "1000.00",
):
    user = UserRepository(db_session).create(
        email=email,
        username=username,
        password_hash=hash_password(password),
        role=role,
        status=status,
    )
    user.balance = Decimal(balance)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client, *, email: str, password: str = "password123"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
