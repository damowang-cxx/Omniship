from app.routers.air_waybills import get_scraper
from app.repositories.audit_log_repository import AuditLogRepository
from app.db.models import AuditLog
from sqlalchemy import select

from tests.auth_helpers import create_test_user, login


class FakeSettings:
    omniship_username = "secret-user"
    omniship_password = "secret-pass"


class FakeScraper:
    settings = FakeSettings()

    async def scrape_air_waybills(self):
        return [
            {
                "number": "123456",
                "status": "Released",
                "status_changed_at_raw": "2026-05-10 18:22",
                "weight_kg_raw": "12.50",
                "received_raw": "Yes",
                "parcels_raw": "68 / 68",
                "in_warehouse_raw": "Yes",
                "released_raw": "Yes",
                "outbound_raw": "No",
                "actions_raw": "View",
            }
        ]


class FailingScraper:
    settings = FakeSettings()

    async def scrape_air_waybills(self):
        raise RuntimeError("Login failed for secret-user with secret-pass")


def test_admin_scrape_and_latest_flow(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    login_response = login(client, email="admin@example.com")
    assert login_response.status_code == 200
    client.app.dependency_overrides[get_scraper] = lambda: FakeScraper()

    scrape_response = client.post("/api/v1/air-waybills/scrape")
    assert scrape_response.status_code == 200
    scrape_body = scrape_response.json()
    assert scrape_body["status"] == "success"
    assert scrape_body["rowCount"] == 1

    latest_response = client.get("/api/v1/air-waybills/latest")
    assert latest_response.status_code == 200
    latest_body = latest_response.json()
    assert latest_body["latestRun"]["status"] == "success"
    assert latest_body["items"][0]["number"] == "123456"
    assert latest_body["items"][0]["parcelsRaw"] == "68 / 68"

    status_response = client.get("/api/v1/air-waybills/scrape-status")
    assert status_response.status_code == 200
    assert status_response.json()["latestRun"]["rowCount"] == 1
    audit_log = db_session.execute(
        select(AuditLog).where(AuditLog.action == "trigger_scrape")
    ).scalar_one_or_none()
    assert audit_log is not None


def test_scrape_failure_records_sanitized_error(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    assert login(client, email="admin@example.com").status_code == 200
    client.app.dependency_overrides[get_scraper] = lambda: FailingScraper()

    scrape_response = client.post("/api/v1/air-waybills/scrape")
    assert scrape_response.status_code == 200
    body = scrape_response.json()

    assert body["status"] == "failed"
    assert "secret-user" not in body["errorMessage"]
    assert "secret-pass" not in body["errorMessage"]
    assert "[redacted]" in body["errorMessage"]


def test_regular_user_can_read_latest_but_cannot_scrape(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    latest_response = client.get("/api/v1/air-waybills/latest")
    assert latest_response.status_code == 200

    scrape_response = client.post("/api/v1/air-waybills/scrape")
    assert scrape_response.status_code == 403

    status_response = client.get("/api/v1/air-waybills/scrape-status")
    assert status_response.status_code == 403


def test_regular_user_only_sees_bound_waybills(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    create_test_user(db_session, email="user@example.com", username="User")
    create_test_user(db_session, email="other@example.com", username="Other")

    assert login(client, email="admin@example.com").status_code == 200
    client.app.dependency_overrides[get_scraper] = lambda: FakeScraper()
    assert client.post("/api/v1/air-waybills/scrape").status_code == 200

    assert login(client, email="user@example.com").status_code == 200
    latest_response = client.get("/api/v1/air-waybills/latest")
    assert latest_response.status_code == 200
    assert latest_response.json()["items"] == []

    upload_response = client.post(
        "/api/v1/waybill-uploads",
        json={"numbers": ["123456", "123-456"]},
    )
    assert upload_response.status_code == 201
    assert upload_response.json()["boundCount"] == 1
    assert upload_response.json()["skippedCount"] == 1

    latest_response = client.get("/api/v1/air-waybills/latest")
    assert latest_response.status_code == 200
    latest_body = latest_response.json()
    assert [item["number"] for item in latest_body["items"]] == ["123456"]

    detail_response = client.get("/api/v1/air-waybills/123456")
    assert detail_response.status_code == 200
    assert detail_response.json()["summary"]["number"] == "123456"

    assert login(client, email="other@example.com").status_code == 200
    assert client.get("/api/v1/air-waybills/123456").status_code == 404

    audit_log = db_session.execute(
        select(AuditLog).where(AuditLog.action == "upload_waybill_numbers")
    ).scalar_one_or_none()
    assert audit_log is not None
