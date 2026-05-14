import pytest

from app.services.auth_service import create_admin_user


def test_create_admin_user_success_and_duplicate_failure(db_session):
    user = create_admin_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        password="password123",
    )

    assert user.email == "admin@example.com"
    assert user.role == "admin"

    with pytest.raises(ValueError, match="already exists"):
        create_admin_user(
            db_session,
            email="admin@example.com",
            username="Admin 2",
            password="password123",
        )
