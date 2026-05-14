from sqlalchemy import select

from app.db.models import AuditLog
from tests.auth_helpers import create_test_user, login


def test_me_requires_session(client):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_login_sets_cookie_and_me_returns_user(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )

    login_response = login(client, email="admin@example.com")
    assert login_response.status_code == 200
    assert "integrer_session" in login_response.cookies

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["user"]["email"] == "admin@example.com"


def test_wrong_password_and_disabled_user_cannot_login(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    wrong_response = login(client, email="user@example.com", password="wrong-password")
    assert wrong_response.status_code == 401

    create_test_user(
        db_session,
        email="disabled@example.com",
        username="Disabled",
        status="disabled",
    )
    disabled_response = login(client, email="disabled@example.com")
    assert disabled_response.status_code == 401

    logs = db_session.execute(
        select(AuditLog).where(AuditLog.action == "login_failed")
    ).scalars().all()
    assert len(logs) == 2


def test_logout_revokes_session(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 200

    me_response = client.get("/api/v1/auth/me")
    assert me_response.status_code == 401

