from datetime import datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditLog, WaybillParcel, WaybillPodFile
from app.services.waybill_service import WaybillService
from tests.auth_helpers import create_test_user, login
from tests.test_waybill_uploads_api import (
    pre_alert_data,
    pre_alert_files,
    pre_alert_workbook_bytes,
)


def _upload_pre_alert(
    client,
    *,
    number: str = "784-84063276",
    pieces: str = "8",
    excel_content: bytes | None = None,
):
    return client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber=number, pieces=pieces),
        files=pre_alert_files(excel_content=excel_content),
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
    assert item["airportOfDeparture"] == "HKG"
    assert item["airportOfArrival"] == "AMS"
    assert item["weightKg"] == "12.500"
    assert item["pieces"] == 12
    assert item["receivedCount"] == 0
    assert item["receivedTotal"] == 12
    assert item["inWarehouseCount"] == 0
    assert item["palletCount"] == 0
    assert item["fycoStatus"] is None
    assert item["releasedCount"] == 0
    assert item["outboundCount"] == 0
    assert item["noaAt"] is None
    assert item["collectionAt"] is None
    assert item["scannedAt"] is None
    assert item["customsClearanceAt"] is None
    assert item["outboundAt"] is None
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
            "palletCount": 4,
            "fycoStatus": "fyco",
            "releasedCount": 1,
            "outboundCount": 0,
            "noaAt": "2026-05-11T12:30:00Z",
            "collectionAt": "2026-05-11T14:15:00Z",
        },
    )
    assert progress_response.status_code == 200
    progress_body = progress_response.json()
    assert progress_body["receivedCount"] == 3
    assert progress_body["inWarehouseCount"] == 2
    assert progress_body["palletCount"] == 4
    assert progress_body["fycoStatus"] == "fyco"
    assert progress_body["noaAt"].startswith("2026-05-11T12:30:00")
    assert progress_body["collectionAt"].startswith("2026-05-11T14:15:00")
    assert progress_body["statusChangedAt"] == original_status_changed_at

    clearance_response = client.patch(
        f"/api/v1/waybills/{public_code}",
        json={"fycoStatus": None},
    )
    assert clearance_response.status_code == 200
    assert clearance_response.json()["fycoStatus"] is None

    clear_response = client.patch(
        f"/api/v1/waybills/{public_code}",
        json={"noaAt": None},
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["noaAt"] is None

    status_response = client.patch(
        f"/api/v1/waybills/{public_code}",
        json={"status": "cleared"},
    )
    assert status_response.status_code == 200
    status_body = status_response.json()
    assert status_body["status"] == "cleared"
    assert datetime.fromisoformat(
        status_body["statusChangedAt"].replace("Z", "+00:00")
    ) >= datetime.fromisoformat(original_status_changed_at.replace("Z", "+00:00"))

    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
        if row.actor_user_id == admin.id
    }
    assert "update_waybill_tracking" in actions


def test_parcels_are_parsed_read_and_bulk_updated(client, db_session):
    admin = create_test_user(
        db_session, email="admin@example.com", username="Admin", role="admin"
    )
    create_test_user(db_session, email="owner@example.com", username="Owner")
    create_test_user(db_session, email="other@example.com", username="Other")
    excel_content = pre_alert_workbook_bytes(
        [
            {
                "parcel_unit_number": "CP148956844DE",
                "destination": "ES",
                "u": 14,
                "weight": "7.460",
                "name": "Jane Doe",
                "address": "1 Test Street",
                "value": 12.5,
            },
            {
                "parcel_unit_number": "CG148125160DE",
                "destination": "意大利",
                "u": "13.00",
                "weight": 9.31,
                "name": "John Doe",
                "address": "2 Test Street",
                "value": 20,
            },
        ]
    )

    assert login(client, email="owner@example.com").status_code == 200
    upload_response = _upload_pre_alert(
        client,
        pieces="20",
        excel_content=excel_content,
    )
    assert upload_response.status_code == 201

    assert login(client, email="admin@example.com").status_code == 200
    assert _approve_upload(client, upload_response.json()["uploadId"]).status_code == 200
    public_code = client.get("/api/v1/waybills").json()["items"][0]["publicCode"]

    parcels_response = client.get(f"/api/v1/waybills/{public_code}/parcels")
    assert parcels_response.status_code == 200
    parcels = parcels_response.json()["items"]
    assert [parcel["parcelUnitNumber"] for parcel in parcels] == [
        "CG148125160DE",
        "CP148956844DE",
    ]
    assert parcels[0]["destinationCode"] == "IT"
    assert parcels[0]["destinationName"] == "Italy"
    assert parcels[0]["numberOfItems"] == 13
    assert parcels[0]["weightKg"] == "9.310"
    assert parcels[0]["status"] == "created"
    assert parcels[0]["inbound"] is False
    assert parcels[0]["outbound"] is False
    assert parcels[0]["specialInstruction"] is False
    assert parcels[1]["destinationCode"] == "ES"
    assert parcels[1]["destinationName"] == "Spain"

    assert login(client, email="owner@example.com").status_code == 200
    owner_response = client.get(f"/api/v1/waybills/{public_code}/parcels")
    assert owner_response.status_code == 200
    forbidden_update = client.patch(
        f"/api/v1/waybills/{public_code}/parcels",
        json={
            "parcelIds": [parcels[0]["id"]],
            "status": "inbound",
        },
    )
    assert forbidden_update.status_code == 403

    assert login(client, email="other@example.com").status_code == 200
    other_response = client.get(f"/api/v1/waybills/{public_code}/parcels")
    assert other_response.status_code == 403

    assert login(client, email="admin@example.com").status_code == 200
    update_response = client.patch(
        f"/api/v1/waybills/{public_code}/parcels",
        json={
            "parcelIds": [parcels[0]["id"], parcels[1]["id"]],
            "status": "inbound",
            "inbound": True,
            "outbound": False,
            "specialInstruction": True,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()["items"]
    assert {parcel["status"] for parcel in updated} == {"inbound"}
    assert {parcel["inbound"] for parcel in updated} == {True}
    assert {parcel["outbound"] for parcel in updated} == {False}
    assert {parcel["specialInstruction"] for parcel in updated} == {True}

    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
        if row.actor_user_id == admin.id
    }
    assert "update_waybill_parcels" in actions


def test_historical_approved_waybill_parcels_lazy_parse(client, db_session):
    create_test_user(
        db_session, email="admin@example.com", username="Admin", role="admin"
    )
    create_test_user(db_session, email="owner@example.com", username="Owner")
    excel_content = pre_alert_workbook_bytes(
        [
            {
                "parcel_unit_number": "CP149001196DE",
                "destination": "Hungary",
                "u": 20,
                "weight": "10.450",
                "name": "Jane Doe",
                "address": "1 Test Street",
                "value": 12.5,
            }
        ]
    )

    assert login(client, email="owner@example.com").status_code == 200
    upload_response = _upload_pre_alert(
        client,
        pieces="20",
        excel_content=excel_content,
    )
    assert upload_response.status_code == 201

    assert login(client, email="admin@example.com").status_code == 200
    assert _approve_upload(client, upload_response.json()["uploadId"]).status_code == 200
    public_code = client.get("/api/v1/waybills").json()["items"][0]["publicCode"]

    for parcel in db_session.execute(select(WaybillParcel)).scalars().all():
        db_session.delete(parcel)
    db_session.commit()
    assert db_session.execute(select(WaybillParcel)).scalar_one_or_none() is None

    parcels_response = client.get(f"/api/v1/waybills/{public_code}/parcels")
    assert parcels_response.status_code == 200
    parcels = parcels_response.json()["items"]
    assert len(parcels) == 1
    assert parcels[0]["parcelUnitNumber"] == "CP149001196DE"
    assert parcels[0]["destinationCode"] == "HU"
    assert db_session.execute(select(WaybillParcel)).scalar_one_or_none() is not None


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


def test_admin_uploads_limits_and_deletes_pod_files(
    client,
    db_session,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("UPLOAD_STORAGE_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        create_test_user(
            db_session, email="admin@example.com", username="Admin", role="admin"
        )
        create_test_user(db_session, email="owner@example.com", username="Owner")

        assert login(client, email="owner@example.com").status_code == 200
        upload_response = _upload_pre_alert(client, pieces="4")
        assert upload_response.status_code == 201

        assert login(client, email="admin@example.com").status_code == 200
        assert _approve_upload(client, upload_response.json()["uploadId"]).status_code == 200
        public_code = client.get("/api/v1/waybills").json()["items"][0]["publicCode"]

        first_upload = client.post(
            f"/api/v1/waybills/{public_code}/pod",
            files={
                "podFile": (
                    "proof-one.pdf",
                    b"%PDF-1.4\nproof one",
                    "application/pdf",
                )
            },
        )
        assert first_upload.status_code == 201
        first_body = first_upload.json()
        assert len(first_body["podFiles"]) == 1
        first_file_id = first_body["podFiles"][0]["id"]
        assert first_body["podFiles"][0]["originalFilename"] == "proof-one.pdf"

        second_upload = client.post(
            f"/api/v1/waybills/{public_code}/pod",
            files={
                "podFile": (
                    "proof-two.jpg",
                    b"\xff\xd8\xff proof two",
                    "image/jpeg",
                )
            },
        )
        assert second_upload.status_code == 201
        second_body = second_upload.json()
        assert len(second_body["podFiles"]) == 2
        second_file_id = next(
            item["id"]
            for item in second_body["podFiles"]
            if item["originalFilename"] == "proof-two.jpg"
        )

        third_upload = client.post(
            f"/api/v1/waybills/{public_code}/pod",
            files={
                "podFile": (
                    "proof-three.png",
                    b"\x89PNG\r\n\x1a\nproof three",
                    "image/png",
                )
            },
        )
        assert third_upload.status_code == 400
        assert "up to 2" in third_upload.json()["detail"]

        pod_file = db_session.execute(
            select(WaybillPodFile).where(WaybillPodFile.id == UUID(first_file_id))
        ).scalar_one()
        stored_path = Path(pod_file.storage_path)
        assert stored_path.is_file()

        assert login(client, email="owner@example.com").status_code == 200
        forbidden_upload = client.post(
            f"/api/v1/waybills/{public_code}/pod",
            files={
                "podFile": (
                    "owner-proof.pdf",
                    b"%PDF-1.4\nowner proof",
                    "application/pdf",
                )
            },
        )
        assert forbidden_upload.status_code == 403

        download_response = client.get(
            f"/api/v1/waybills/{public_code}/pod/{second_file_id}/download"
        )
        assert download_response.status_code == 200
        assert download_response.headers["content-type"].startswith("image/jpeg")
        assert download_response.content.startswith(b"\xff\xd8\xff")

        forbidden_delete = client.delete(
            f"/api/v1/waybills/{public_code}/pod/{first_file_id}"
        )
        assert forbidden_delete.status_code == 403
        assert stored_path.is_file()

        assert login(client, email="admin@example.com").status_code == 200
        delete_response = client.delete(
            f"/api/v1/waybills/{public_code}/pod/{first_file_id}"
        )
        assert delete_response.status_code == 200
        assert delete_response.json() == {"status": "deleted", "podFileId": first_file_id}
        assert not stored_path.exists()
        assert (
            db_session.execute(
                select(WaybillPodFile).where(WaybillPodFile.id == UUID(first_file_id))
            ).scalar_one_or_none()
            is None
        )

        png_upload = client.post(
            f"/api/v1/waybills/{public_code}/pod",
            files={
                "podFile": (
                    "proof-three.png",
                    b"\x89PNG\r\n\x1a\nproof three",
                    "image/png",
                )
            },
        )
        assert png_upload.status_code == 201
        assert any(
            item["originalFilename"] == "proof-three.png"
            for item in png_upload.json()["podFiles"]
        )

        actions = {row.action for row in db_session.execute(select(AuditLog)).scalars()}
        assert "upload_waybill_pod_file" in actions
        assert "download_waybill_pod_file" in actions
        assert "delete_waybill_pod_file" in actions
    finally:
        get_settings.cache_clear()


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
