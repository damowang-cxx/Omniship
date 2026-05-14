from sqlalchemy import select

from app.db.models import AuditLog
from tests.auth_helpers import create_test_user, login


def test_admin_can_manage_users(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    assert login(client, email="admin@example.com").status_code == 200

    create_response = client.post(
        "/api/v1/users",
        json={
            "email": "operator@example.com",
            "username": "Operator",
            "password": "password123",
        },
    )
    assert create_response.status_code == 201
    user_id = create_response.json()["id"]
    assert create_response.json()["role"] == "user"

    list_response = client.get("/api/v1/users")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 2

    disable_response = client.patch(f"/api/v1/users/{user_id}", json={"status": "disabled"})
    assert disable_response.status_code == 200
    assert disable_response.json()["status"] == "disabled"

    reset_response = client.post(
        f"/api/v1/users/{user_id}/reset-password",
        json={"password": "newpassword123"},
    )
    assert reset_response.status_code == 200

    actions = [
        row.action
        for row in db_session.execute(select(AuditLog).order_by(AuditLog.created_at)).scalars()
    ]
    assert "create_user" in actions
    assert "disable_user" in actions
    assert "reset_password" in actions


def test_regular_user_cannot_manage_users(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.get("/api/v1/users")

    assert response.status_code == 403

