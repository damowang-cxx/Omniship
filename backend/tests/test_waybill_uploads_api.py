import pytest

from app.db.models import AuditLog, WaybillUserBinding
from app.repositories.waybill_user_binding_repository import normalize_waybill_number
from app.services.alline_waybill_uploader import AllineWaybillUploadError
from sqlalchemy import select

from tests.auth_helpers import create_test_user, login


class FakeAllineWaybillUploader:
    calls: list[str] = []

    def __init__(self, settings=None):
        self.settings = settings

    async def submit_upload(self, upload):
        self.calls.append(upload.air_waybill_number)


@pytest.fixture(autouse=True)
def fake_alline_uploader(monkeypatch):
    FakeAllineWaybillUploader.calls = []
    monkeypatch.setattr(
        "app.services.waybill_upload_service.AllineWaybillUploader",
        FakeAllineWaybillUploader,
    )
    return FakeAllineWaybillUploader


def pre_alert_files(
    *,
    pdf_name: str = "awb.pdf",
    excel_name: str = "pre-alert.xlsx",
    pdf_content: bytes = b"%PDF-1.4\ncontent",
    excel_content: bytes = b"excel-content",
):
    return [
        ("airWaybillDocuments", (pdf_name, pdf_content, "application/pdf")),
        (
            "preAlertFile",
            (
                excel_name,
                excel_content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ),
        ),
    ]


def pre_alert_data(**overrides):
    data = {
        "platform": "ALLINE",
        "shipmentType": "Air",
        "airWaybillNumber": "784-84063276",
        "grossWeightKg": "12.5",
        "pieces": "8",
        "arrivalFlightNumber": "EK0147",
    }
    data.update(overrides)
    return data


def test_user_uploads_pre_alert_and_admin_can_review(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    create_test_user(db_session, email="user@example.com", username="User")

    assert login(client, email="user@example.com").status_code == 200
    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201
    upload_body = upload_response.json()
    assert upload_body["platform"] == "ALLINE"
    assert upload_body["airWaybillNumber"] == "784-84063276"
    assert upload_body["status"] == "pending_review"
    assert upload_body["platformSubmissionStatus"] == "success"
    assert upload_body["platformSubmissionMethod"] == "automated"
    assert FakeAllineWaybillUploader.calls == ["784-84063276"]

    user_list_response = client.get("/api/v1/waybill-uploads")
    assert user_list_response.status_code == 200
    assert [item["airWaybillNumber"] for item in user_list_response.json()["items"]] == [
        "784-84063276"
    ]

    assert login(client, email="admin@example.com").status_code == 200
    admin_list_response = client.get("/api/v1/waybill-uploads")
    assert admin_list_response.status_code == 200
    admin_items = admin_list_response.json()["items"]
    assert admin_items[0]["airWaybillNumber"] == "784-84063276"
    assert admin_items[0]["platform"] == "ALLINE"
    assert admin_items[0]["platformSubmissionStatus"] == "success"
    assert admin_items[0]["platformSubmissionMethod"] == "automated"
    assert admin_items[0]["user"]["email"] == "user@example.com"

    review_response = client.patch(
        f"/api/v1/waybill-uploads/{upload_body['uploadId']}/status",
        json={"status": "approved"},
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "approved"

    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
    }
    assert "upload_pre_alert" in actions
    assert "platform_upload_success" in actions
    assert "review_waybill_upload" in actions


def test_pre_alert_upload_rejects_duplicate_number(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    first_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber="784-84063276"),
        files=pre_alert_files(),
    )
    assert first_response.status_code == 201

    duplicate_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber="78484063276"),
        files=pre_alert_files(
            pdf_name="awb-2.pdf",
            excel_name="pre-alert-2.xlsx",
        ),
    )
    assert duplicate_response.status_code == 400
    assert "already been uploaded" in duplicate_response.text


def test_pre_alert_upload_validates_numbers_and_files(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    invalid_platform = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(platform="UNKNOWN"),
        files=pre_alert_files(),
    )
    assert invalid_platform.status_code == 400
    assert "Platform is invalid" in invalid_platform.text

    invalid_weight = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(grossWeightKg="not-a-number"),
        files=pre_alert_files(),
    )
    assert invalid_weight.status_code == 400
    assert "Gross Weight" in invalid_weight.text

    invalid_pdf = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber="176-28780776"),
        files=pre_alert_files(pdf_content=b"not a pdf"),
    )
    assert invalid_pdf.status_code == 400
    assert "must be a PDF" in invalid_pdf.text


def test_pre_alert_upload_records_platform_submission_failure(
    client,
    db_session,
    monkeypatch,
):
    class FailingAllineWaybillUploader:
        def __init__(self, settings=None):
            self.settings = settings

        async def submit_upload(self, upload):
            raise AllineWaybillUploadError("Upload button not found")

    monkeypatch.setattr(
        "app.services.waybill_upload_service.AllineWaybillUploader",
        FailingAllineWaybillUploader,
    )
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201
    upload_body = upload_response.json()
    assert upload_body["platformSubmissionStatus"] == "failed"
    assert upload_body["platformSubmissionMethod"] == "automated"
    assert upload_body["platformSubmissionError"] == "Upload button not found"

    list_response = client.get("/api/v1/waybill-uploads")
    assert list_response.status_code == 200
    item = list_response.json()["items"][0]
    assert item["platformSubmissionStatus"] == "failed"
    assert item["platformSubmissionMethod"] == "automated"
    assert item["platformSubmissionError"] == "Upload button not found"

    bindings_after_failure = db_session.execute(
        select(WaybillUserBinding)
    ).scalars().all()
    assert bindings_after_failure == []

    FakeAllineWaybillUploader.calls = []
    monkeypatch.setattr(
        "app.services.waybill_upload_service.AllineWaybillUploader",
        FakeAllineWaybillUploader,
    )
    retry_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            pdf_name="awb-retry.pdf",
            excel_name="pre-alert-retry.xlsx",
        ),
    )
    assert retry_response.status_code == 201
    retry_body = retry_response.json()
    assert retry_body["platformSubmissionStatus"] == "success"
    assert retry_body["platformSubmissionMethod"] == "automated"
    assert retry_body["platformSubmissionError"] is None
    assert FakeAllineWaybillUploader.calls == ["784-84063276"]

    bindings_after_retry = db_session.execute(
        select(WaybillUserBinding)
    ).scalars().all()
    assert [binding.number for binding in bindings_after_retry] == ["784-84063276"]

    retry_list_response = client.get("/api/v1/waybill-uploads")
    assert retry_list_response.status_code == 200
    submission_statuses = [
        upload["platformSubmissionStatus"]
        for upload in retry_list_response.json()["items"]
    ]
    assert submission_statuses.count("failed") == 1
    assert submission_statuses.count("success") == 1

    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
    }
    assert "upload_pre_alert" in actions
    assert "platform_upload_failed" in actions
    assert "platform_upload_success" in actions


def test_user_can_delete_local_upload_and_binding(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["uploadId"]

    bindings_before_delete = db_session.execute(
        select(WaybillUserBinding)
    ).scalars().all()
    assert [binding.number for binding in bindings_before_delete] == ["784-84063276"]

    delete_response = client.delete(f"/api/v1/waybill-uploads/{upload_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {
        "status": "deleted",
        "uploadId": upload_id,
        "removedBinding": True,
    }

    list_response = client.get("/api/v1/waybill-uploads")
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []

    bindings_after_delete = db_session.execute(
        select(WaybillUserBinding)
    ).scalars().all()
    assert bindings_after_delete == []

    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
    }
    assert "delete_waybill_upload" in actions


def test_admin_manual_submit_failed_upload_binds_owner(
    client,
    db_session,
    monkeypatch,
):
    class FailingAllineWaybillUploader:
        def __init__(self, settings=None):
            self.settings = settings

        async def submit_upload(self, upload):
            raise AllineWaybillUploadError("Upload records button not found")

    monkeypatch.setattr(
        "app.services.waybill_upload_service.AllineWaybillUploader",
        FailingAllineWaybillUploader,
    )
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    user = create_test_user(db_session, email="user@example.com", username="User")

    assert login(client, email="user@example.com").status_code == 200
    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["uploadId"]
    assert upload_response.json()["platformSubmissionStatus"] == "failed"

    assert login(client, email="admin@example.com").status_code == 200
    manual_response = client.post(
        f"/api/v1/waybill-uploads/{upload_id}/manual-submit"
    )
    assert manual_response.status_code == 200
    manual_body = manual_response.json()
    assert manual_body["platformSubmissionStatus"] == "success"
    assert manual_body["platformSubmissionMethod"] == "manual"
    assert manual_body["platformSubmissionError"] is None
    assert manual_body["platformSubmittedAt"] is not None

    bindings = db_session.execute(select(WaybillUserBinding)).scalars().all()
    assert [(binding.user_id, binding.number) for binding in bindings] == [
        (user.id, "784-84063276")
    ]
    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
    }
    assert "manual_platform_upload_success" in actions


def test_non_admin_cannot_manual_submit_upload(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200
    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201

    manual_response = client.post(
        f"/api/v1/waybill-uploads/{upload_response.json()['uploadId']}/manual-submit"
    )
    assert manual_response.status_code == 403


def test_success_upload_requires_force_for_manual_submit(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    create_test_user(db_session, email="user@example.com", username="User")

    assert login(client, email="user@example.com").status_code == 200
    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["uploadId"]

    assert login(client, email="admin@example.com").status_code == 200
    no_force_response = client.post(
        f"/api/v1/waybill-uploads/{upload_id}/manual-submit"
    )
    assert no_force_response.status_code == 400
    assert "force=true" in no_force_response.text

    force_response = client.post(
        f"/api/v1/waybill-uploads/{upload_id}/manual-submit?force=true"
    )
    assert force_response.status_code == 200
    assert force_response.json()["platformSubmissionMethod"] == "manual"


def test_manual_submit_rejects_number_bound_to_another_user(
    client,
    db_session,
    monkeypatch,
):
    class FailingAllineWaybillUploader:
        def __init__(self, settings=None):
            self.settings = settings

        async def submit_upload(self, upload):
            raise AllineWaybillUploadError("Upload records button not found")

    monkeypatch.setattr(
        "app.services.waybill_upload_service.AllineWaybillUploader",
        FailingAllineWaybillUploader,
    )
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    create_test_user(db_session, email="user@example.com", username="User")
    other_user = create_test_user(
        db_session,
        email="other@example.com",
        username="Other",
    )

    assert login(client, email="user@example.com").status_code == 200
    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["uploadId"]

    db_session.add(
        WaybillUserBinding(
            user_id=other_user.id,
            number="784-84063276",
            normalized_number=normalize_waybill_number("784-84063276"),
            source="upload",
        )
    )
    db_session.commit()

    assert login(client, email="admin@example.com").status_code == 200
    manual_response = client.post(
        f"/api/v1/waybill-uploads/{upload_id}/manual-submit"
    )
    assert manual_response.status_code == 400
    assert "already bound to another user" in manual_response.text


def test_admin_filters_uploads_and_users_cannot_filter_into_other_users(
    client,
    db_session,
):
    admin = create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    user = create_test_user(db_session, email="user@example.com", username="User")
    other_user = create_test_user(
        db_session,
        email="other@example.com",
        username="Other",
    )

    assert login(client, email="user@example.com").status_code == 200
    first_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber="784-84063276"),
        files=pre_alert_files(pdf_name="first.pdf", excel_name="first.xlsx"),
    )
    assert first_response.status_code == 201

    assert login(client, email="other@example.com").status_code == 200
    second_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber="176-28780776"),
        files=pre_alert_files(pdf_name="second.pdf", excel_name="second.xlsx"),
    )
    assert second_response.status_code == 201

    assert login(client, email="admin@example.com").status_code == 200
    user_filter_response = client.get(f"/api/v1/waybill-uploads?userId={user.id}")
    assert user_filter_response.status_code == 200
    assert [
        item["airWaybillNumber"]
        for item in user_filter_response.json()["items"]
    ] == ["784-84063276"]

    number_filter_response = client.get("/api/v1/waybill-uploads?q=17628780776")
    assert number_filter_response.status_code == 200
    assert [
        item["airWaybillNumber"]
        for item in number_filter_response.json()["items"]
    ] == ["176-28780776"]

    status_filter_response = client.get(
        "/api/v1/waybill-uploads?platformSubmissionStatus=success&status=pending_review"
    )
    assert status_filter_response.status_code == 200
    assert len(status_filter_response.json()["items"]) == 2

    assert login(client, email="other@example.com").status_code == 200
    user_scope_response = client.get(f"/api/v1/waybill-uploads?userId={user.id}")
    assert user_scope_response.status_code == 200
    assert [
        item["airWaybillNumber"]
        for item in user_scope_response.json()["items"]
    ] == ["176-28780776"]

    assert admin.role == "admin"
    assert other_user.email == "other@example.com"


def test_upload_file_download_permissions_and_audit(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    create_test_user(db_session, email="user@example.com", username="User")
    create_test_user(db_session, email="other@example.com", username="Other")

    pdf_content = b"%PDF-1.4\nmanual-fallback"
    assert login(client, email="user@example.com").status_code == 200
    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(pdf_content=pdf_content),
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["uploadId"]
    list_response = client.get("/api/v1/waybill-uploads")
    pdf_file = next(
        file
        for file in list_response.json()["items"][0]["files"]
        if file["fileKind"] == "air_waybill_document"
    )

    owner_download = client.get(
        f"/api/v1/waybill-uploads/{upload_id}/files/{pdf_file['id']}/download"
    )
    assert owner_download.status_code == 200
    assert owner_download.content == pdf_content
    assert "awb.pdf" in owner_download.headers["content-disposition"]

    assert login(client, email="other@example.com").status_code == 200
    other_download = client.get(
        f"/api/v1/waybill-uploads/{upload_id}/files/{pdf_file['id']}/download"
    )
    assert other_download.status_code == 403

    assert login(client, email="admin@example.com").status_code == 200
    admin_download = client.get(
        f"/api/v1/waybill-uploads/{upload_id}/files/{pdf_file['id']}/download"
    )
    assert admin_download.status_code == 200
    assert admin_download.content == pdf_content

    actions = [
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
    ]
    assert actions.count("download_waybill_upload_file") == 2
