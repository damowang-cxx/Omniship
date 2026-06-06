from datetime import datetime

from sqlalchemy import select

from app.db.models import AuditLog
from app.services.waybill_service import WaybillService
from tests.auth_helpers import create_test_user, login
from tests.test_waybill_uploads_api import pre_alert_data, pre_alert_files


def _upload_pre_alert(client, *, number: str = "784-84063276", pieces: str = "8"):
    return client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber=number, pieces=pieces),
        files=pre_alert_files(),
    )


def _approve_upload(client, upload_id: str):
    return client.patch(
        f"/api/v1/waybill-uploads/{upload_id}/status",
        json={"status": "approved"},
    )


def test_approved_upload_creates_waybill_tracking_record(client, db_session):
    create_test_user(db_session, email="admin@example.com", username="Admin", role="admin")
    create_test_user(db_session, email="user@example.com", username="User")
    create_test_user(db_session, email="other@example.com", username="Other")

    assert login(client, email="user@example.com").status_code == 200
    upload_response = _upload_pre_alert(client, pieces="12")
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["uploadId"]

    empty_response = client.get("/api/v1/waybills")
    assert empty_response.status_code == 200
    assert empty_response.json()["items"] == []

    assert login(client, email="admin@example.com").status_code == 200
    review_response = _approve_upload(client, upload_id)
    assert review_response.status_code == 200

    admin_list_response = client.get("/api/v1/waybills")
    assert admin_list_response.status_code == 200
    admin_items = admin_list_response.json()["items"]
    assert len(admin_items) == 1
    item = admin_items[0]
    assert item["publicCode"]
    assert len(item["publicCode"]) == 8
    assert item["number"] == "784-84063276"
    assert item["status"] == "created"
    assert item["weightKg"] == "12.500"
    assert item["pieces"] == 12
    assert item["receivedCount"] == 0
    assert item["receivedTotal"] == 12
    assert item["inWarehouseCount"] == 0
    assert item["releasedCount"] == 0
    assert item["outboundCount"] == 0
    assert item["user"]["email"] == "user@example.com"

    assert login(client, email="user@example.com").status_code == 200
    user_list_response = client.get("/api/v1/waybills")
    assert user_list_response.status_code == 200
    assert [row["number"] for row in user_list_response.json()["items"]] == [
        "784-84063276"
    ]

    assert login(client, email="other@example.com").status_code == 200
    other_list_response = client.get("/api/v1/waybills")
    assert other_list_response.status_code == 200
    assert other_list_response.json()["items"] == []


def test_admin_filters_and_updates_waybill_tracking(client, db_session):
    admin = create_test_user(
        db_session, email="admin@example.com", username="Admin", role="admin"
    )
    user = create_test_user(db_session, email="user@example.com", username="User")

    assert login(client, email="user@example.com").status_code == 200
    upload_response = _upload_pre_alert(client, number="176-28780776", pieces="10")
    assert upload_response.status_code == 201

    assert login(client, email="admin@example.com").status_code == 200
    assert _approve_upload(client, upload_response.json()["uploadId"]).status_code == 200

    filtered_response = client.get(
        f"/api/v1/waybills?userId={user.id}&status=created&q=17628780776"
    )
    assert filtered_response.status_code == 200
    item = filtered_response.json()["items"][0]
    public_code = item["publicCode"]
    original_status_changed_at = item["statusChangedAt"]

    progress_response = client.patch(
        f"/api/v1/waybills/{public_code}",
        json={
            "receivedCount": 3,
            "receivedTotal": 10,
            "inWarehouseCount": 2,
            "releasedCount": 1,
            "outboundCount": 0,
        },
    )
    assert progress_response.status_code == 200
    progress_body = progress_response.json()
    assert progress_body["receivedCount"] == 3
    assert progress_body["inWarehouseCount"] == 2
    assert progress_body["statusChangedAt"] == original_status_changed_at

    status_response = client.patch(
        f"/api/v1/waybills/{public_code}",
        json={"status": "inbound"},
    )
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "inbound"
    assert datetime.fromisoformat(
        status_body["statusChangedAt"].replace("Z", "+00:00")
    ) >= datetime.fromisoformat(original_status_changed_at.replace("Z", "+00:00"))

    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
        if row.actor_user_id == admin.id
    }
    assert "update_waybill_tracking" in actions


def test_regular_user_cannot_update_or_read_another_waybill(client, db_session):
    create_test_user(db_session, email="admin@example.com", username="Admin", role="admin")
    create_test_user(db_session, email="owner@example.com", username="Owner")
    create_test_user(db_session, email="other@example.com", username="Other")

    assert login(client, email="owner@example.com").status_code == 200
    upload_response = _upload_pre_alert(client)
    assert upload_response.status_code == 201

    assert login(client, email="admin@example.com").status_code == 200
    assert _approve_upload(client, upload_response.json()["uploadId"]).status_code == 200
    public_code = client.get("/api/v1/waybills").json()["items"][0]["publicCode"]

    assert login(client, email="other@example.com").status_code == 200
    detail_response = client.get(f"/api/v1/waybills/{public_code}")
    assert detail_response.status_code == 403

    update_response = client.patch(
        f"/api/v1/waybills/{public_code}",
        json={"status": "inbound"},
    )
    assert update_response.status_code == 403


def test_public_code_generation_retries_duplicate(client, db_session, monkeypatch):
    create_test_user(db_session, email="admin@example.com", username="Admin", role="admin")
    create_test_user(db_session, email="user@example.com", username="User")

    assert login(client, email="user@example.com").status_code == 200
    first_upload = _upload_pre_alert(client, number="784-84063276")
    second_upload = _upload_pre_alert(client, number="784-84063277")
    assert first_upload.status_code == 201
    assert second_upload.status_code == 201

    assert login(client, email="admin@example.com").status_code == 200
    assert _approve_upload(client, first_upload.json()["uploadId"]).status_code == 200
    existing_code = client.get("/api/v1/waybills").json()["items"][0]["publicCode"]
    generated_codes = iter([existing_code, "ZXCVBN12"])

    def fake_generate_public_code(self):
        return next(generated_codes)

    monkeypatch.setattr(
        WaybillService,
        "_generate_public_code",
        fake_generate_public_code,
    )

    assert _approve_upload(client, second_upload.json()["uploadId"]).status_code == 200
    codes = {item["publicCode"] for item in client.get("/api/v1/waybills").json()["items"]}
    assert existing_code in codes
    assert "ZXCVBN12" in codes
