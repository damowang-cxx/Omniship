from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.models import AuditLog, UserSession
from tests.auth_helpers import create_test_user, login
from tests.test_downstream_sync import create_waybill


def start(client, user):
    return client.post("/api/v1/auth/impersonation", json={"userId": str(user.id)})


def test_admin_enters_customer_permissions_and_can_return(client, db_session):
    admin, customer, record = create_waybill(db_session)
    other = create_test_user(db_session, email="other@example.com")
    login(client, email=admin.email)
    customer_password = customer.password_hash
    customer_last_login = customer.last_login_at
    response = start(client, customer)
    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(customer.id)
    assert response.json()["user"]["role"] == "user"
    assert response.json()["user"]["impersonating"] is True
    assert client.get("/api/v1/auth/me").json()["user"]["impersonating"] is True
    assert client.get("/api/v1/billing/me").json()["user"]["id"] == str(customer.id)
    # Supplying a different user ID cannot widen the effective customer's scope.
    waybills = client.get(f"/api/v1/waybills?userId={other.id}").json()["items"]
    assert [item["publicCode"] for item in waybills] == [record.public_code]
    assert client.get("/api/v1/users").status_code == 403
    assert client.get("/api/v1/admin/downstream/bindings").status_code == 403
    assert client.patch(f"/api/v1/users/{other.id}", json={"status": "disabled"}).status_code == 403
    assert start(client, other).status_code == 403
    db_session.refresh(customer)
    assert customer.password_hash == customer_password
    assert customer.last_login_at == customer_last_login
    # Customer operations keep their actual administrator attribution in the audit log.
    assert client.get("/api/v1/billing/me/export").status_code == 200
    export_log = db_session.scalars(select(AuditLog).where(AuditLog.action == "export_billing_excel")).one()
    assert export_log.actor_user_id == admin.id
    assert export_log.audit_metadata["impersonatedUserId"] == str(customer.id)
    response = client.delete("/api/v1/auth/impersonation")
    assert response.status_code == 200
    assert response.json()["user"]["id"] == str(admin.id)
    assert response.json()["user"]["impersonating"] is False
    assert client.get("/api/v1/users").status_code == 200
    for action in ("start_impersonation", "stop_impersonation"):
        log = db_session.scalars(select(AuditLog).where(AuditLog.action == action)).one()
        assert log.actor_user_id == admin.id
        assert log.target_id == str(customer.id)


def test_customer_and_anonymous_sessions_cannot_impersonate_or_return(client, db_session):
    customer = create_test_user(db_session, email="user@example.com")
    assert start(client, customer).status_code == 401
    assert client.delete("/api/v1/auth/impersonation").status_code == 401
    login(client, email=customer.email)
    assert start(client, customer).status_code == 403
    assert client.delete("/api/v1/auth/impersonation").status_code == 403
    assert client.get("/api/v1/auth/me").json()["user"]["impersonating"] is False


@pytest.mark.parametrize("role,status", [("admin", "active"), ("user", "disabled")])
def test_only_active_customers_can_be_entered(client, db_session, role, status):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    target = create_test_user(db_session, email="target@example.com", role=role, status=status)
    login(client, email=admin.email)
    assert start(client, target).status_code == 400
    assert client.get("/api/v1/auth/me").json()["user"]["id"] == str(admin.id)
    assert client.post("/api/v1/auth/impersonation", json={"userId": str(uuid4())}).status_code == 400


@pytest.mark.parametrize("change", ["disabled", "promoted"])
def test_unavailable_customer_is_blocked_but_administrator_can_return(client, db_session, change):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com")
    login(client, email=admin.email)
    assert start(client, customer).status_code == 200
    if change == "disabled":
        customer.status = "disabled"
    else:
        customer.role = "admin"
    db_session.commit()
    profile = client.get("/api/v1/auth/me")
    assert profile.status_code == 200
    assert profile.json()["user"]["role"] == "user"
    assert profile.json()["user"]["impersonating"] is True
    assert client.get("/api/v1/billing/me").status_code == 403
    assert client.get("/api/v1/users").status_code == 403
    assert client.delete("/api/v1/auth/impersonation").status_code == 200
    assert client.get("/api/v1/users").status_code == 200


@pytest.mark.parametrize("change", ["disabled", "demoted", "expired", "revoked"])
def test_invalid_administrator_session_cannot_access_customer_or_restore_admin(client, db_session, change):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com")
    login(client, email=admin.email)
    start(client, customer)
    session = db_session.scalars(select(UserSession).where(UserSession.user_id == admin.id)).one()
    if change == "disabled":
        admin.status = "disabled"
    elif change == "demoted":
        admin.role = "user"
    elif change == "expired":
        session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    else:
        session.revoked_at = datetime.now(timezone.utc)
    db_session.commit()
    expected = 401 if change in {"expired", "revoked"} else 403
    assert client.get("/api/v1/auth/me").status_code == expected
    assert client.delete("/api/v1/auth/impersonation").status_code == expected


def test_impersonation_is_scoped_to_admin_session_and_logout_preserves_customer_session(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com")
    login(client, email=customer.email)
    customer_cookie = client.cookies.get("integrer_session")
    login(client, email=admin.email)
    second_admin_cookie = client.cookies.get("integrer_session")
    login(client, email=admin.email)
    admin_cookie = client.cookies.get("integrer_session")
    start(client, customer)
    client.cookies.set("integrer_session", second_admin_cookie)
    assert client.get("/api/v1/auth/me").json()["user"]["role"] == "admin"
    client.cookies.set("integrer_session", customer_cookie)
    assert client.get("/api/v1/auth/me").json()["user"]["impersonating"] is False
    client.cookies.set("integrer_session", admin_cookie)
    assert client.get("/api/v1/auth/me").json()["user"]["impersonating"] is True
    assert client.post("/api/v1/auth/logout").status_code == 200
    client.cookies.set("integrer_session", admin_cookie)
    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("integrer_session", customer_cookie)
    assert client.get("/api/v1/auth/me").status_code == 200
