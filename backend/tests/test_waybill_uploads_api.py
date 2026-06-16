from io import BytesIO

from app.db.models import AuditLog
from sqlalchemy import select

from tests.auth_helpers import create_test_user, login


def pre_alert_files(
    *,
    pdf_name: str = "awb.pdf",
    excel_name: str = "pre-alert.xlsx",
    pdf_content: bytes = b"%PDF-1.4\ncontent",
    excel_content: bytes | None = None,
):
    excel_content = excel_content or pre_alert_workbook_bytes()
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
        "shipmentType": "Air",
        "airWaybillNumber": "784-84063276",
        "grossWeightKg": "12.5",
        "pieces": "8",
        "arrivalFlightNumber": "EK0147",
        "airportOfDeparture": "HKG",
        "airportOfArrival": "AMS",
    }
    data.update(overrides)
    return data


def pre_alert_workbook_bytes(rows: list[dict] | None = None) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    headers = [f"Column {index}" for index in range(1, 30)]
    headers[8] = "parcel unit number"
    headers[11] = "name"
    headers[12] = "thoroughfare"
    headers[18] = "destination"
    headers[20] = "quantity"
    headers[21] = "weight"
    headers[22] = "price"
    sheet.append(headers)
    for row_payload in rows or [
        {
            "name": "Jane Doe",
            "address": "1 Test Street",
            "goods": "Cotton shirt",
            "value": 12.5,
        }
    ]:
        row = [""] * 29
        consistent_values = row_payload.get("a_to_g")
        if consistent_values:
            for index, value in enumerate(consistent_values[:7]):
                row[index] = value
        else:
            for index, key in enumerate(("a", "b", "c", "d", "e", "f", "g")):
                row[index] = row_payload.get(key, "")
        row[11] = row_payload.get("name", "")
        row[12] = row_payload.get("address", "")
        row[13] = row_payload.get("n", "")
        row[14] = row_payload.get("o", "")
        row[16] = row_payload.get("q", "")
        row[8] = row_payload.get("parcel_unit_number", "")
        row[18] = row_payload.get("destination", row_payload.get("goods", ""))
        row[20] = row_payload.get("u", "")
        row[21] = row_payload.get("weight", "")
        row[22] = row_payload.get("value", "")
        row[28] = row_payload.get("ac", "")
        sheet.append(row)

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


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
    assert upload_body["airWaybillNumber"] == "784-84063276"
    assert upload_body["airportOfDeparture"] == "HKG"
    assert upload_body["airportOfArrival"] == "AMS"
    assert upload_body["status"] == "pending_review"
    assert upload_body["boundUserId"]
    assert "platform" not in upload_body
    assert "platformSubmissionStatus" not in upload_body

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
    assert admin_items[0]["airportOfDeparture"] == "HKG"
    assert admin_items[0]["airportOfArrival"] == "AMS"
    assert admin_items[0]["status"] == "pending_review"
    assert admin_items[0]["user"]["email"] == "user@example.com"
    assert "platform" not in admin_items[0]

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
    assert "review_waybill_upload" in actions


def test_pre_alert_upload_allows_duplicate_number(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    first_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber="784-84063276"),
        files=pre_alert_files(),
    )
    assert first_response.status_code == 201

    # The same normalized number can be uploaded again because local uploads
    # no longer use external-platform de-duplication or binding rules.
    duplicate_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(airWaybillNumber="78484063276"),
        files=pre_alert_files(
            pdf_name="awb-2.pdf",
            excel_name="pre-alert-2.xlsx",
        ),
    )
    assert duplicate_response.status_code == 201

    list_response = client.get("/api/v1/waybill-uploads")
    assert list_response.status_code == 200
    assert len(list_response.json()["items"]) == 2


def test_pre_alert_upload_validates_weight_and_pdf(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

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


def test_pre_alert_upload_temporarily_allows_any_pre_alert_file(client, db_session):
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
        files=pre_alert_files(
            excel_name="pre-alert.txt",
            excel_content=b"not an excel workbook",
        ),
    )
    assert upload_response.status_code == 201

    assert login(client, email="admin@example.com").status_code == 200
    review_response = client.patch(
        f"/api/v1/waybill-uploads/{upload_response.json()['uploadId']}/status",
        json={"status": "approved"},
    )
    assert review_response.status_code == 200
    assert review_response.json()["status"] == "approved"


def test_pre_alert_upload_no_longer_rejects_old_banned_goods_column(
    client,
    db_session,
):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "goods": "Portable vacuum cleaner",
                        "value": 12.5,
                    }
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_allows_same_recipient_address_at_150_eur(
    client,
    db_session,
):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "goods": "Cotton shirt",
                        "value": 100,
                    },
                    {
                        "name": " jane   doe ",
                        "address": "1 test street",
                        "goods": "Book",
                        "value": "50.00",
                    },
                    {
                        "name": "Jane Doe",
                        "address": "2 Test Street",
                        "goods": "Shoes",
                        "value": 149,
                    },
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_temporarily_allows_same_recipient_address_over_150_eur(
    client,
    db_session,
):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "goods": "Cotton shirt",
                        "value": 100,
                    },
                    {
                        "name": " jane   doe ",
                        "address": "1 test street",
                        "goods": "Book",
                        "value": "50.01",
                    },
                    {
                        "name": "Jane Doe",
                        "address": "2 Test Street",
                        "goods": "Shoes",
                        "value": 149,
                    },
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_temporarily_allows_invalid_w_amount(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "value": "not-a-number",
                    }
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_temporarily_allows_amount_without_name_or_address(
    client,
    db_session,
):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [{"name": "", "address": "1 Test Street", "value": 12.5}]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_allows_u_at_20_and_matching_a_to_g(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "a_to_g": ["EPIX", "DE", "AIR", "A", "B", "C", "D"],
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "u": 20,
                        "value": 12.5,
                    },
                    {
                        "a_to_g": ["EPIX", "DE", "AIR", "A", "B", "C", "D"],
                        "name": "John Doe",
                        "address": "2 Test Street",
                        "u": "20.00",
                        "value": 20,
                    },
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_temporarily_allows_u_over_20(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "u": 21,
                        "value": 12.5,
                    }
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_temporarily_allows_filled_n_o_q_ac_columns(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "value": 12.5,
                        "n": "must be empty",
                        "o": "must be empty",
                        "q": "must be empty",
                        "ac": "must be empty",
                    }
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_pre_alert_upload_temporarily_allows_inconsistent_a_to_g_columns(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(
            excel_content=pre_alert_workbook_bytes(
                [
                    {
                        "a_to_g": ["EPIX", "DE", "AIR", "A", "B", "C", "D"],
                        "name": "Jane Doe",
                        "address": "1 Test Street",
                        "value": 12.5,
                    },
                    {
                        "a_to_g": ["EPIX", "FR", "AIR", "A", "B", "C", "D"],
                        "name": "John Doe",
                        "address": "2 Test Street",
                        "value": 20,
                    },
                ]
            )
        ),
    )

    assert response.status_code == 201


def test_non_admin_cannot_upload_for_target_user(client, db_session):
    user = create_test_user(db_session, email="user@example.com", username="User")
    target_user = create_test_user(
        db_session,
        email="target@example.com",
        username="Target",
    )
    assert login(client, email="user@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(targetUserId=str(target_user.id)),
        files=pre_alert_files(),
    )

    assert response.status_code == 403
    assert "Only admins can upload for another user" in response.text
    assert user.email == "user@example.com"


def test_admin_can_upload_for_target_user(client, db_session):
    create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    target_user = create_test_user(
        db_session,
        email="target@example.com",
        username="Target",
    )
    assert login(client, email="admin@example.com").status_code == 200

    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(targetUserId=str(target_user.id)),
        files=pre_alert_files(),
    )

    assert response.status_code == 201
    assert response.json()["boundUserId"] == str(target_user.id)


def test_user_can_delete_local_upload(client, db_session):
    create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email="user@example.com").status_code == 200

    upload_response = client.post(
        "/api/v1/waybill-uploads/file",
        data=pre_alert_data(),
        files=pre_alert_files(),
    )
    assert upload_response.status_code == 201
    upload_id = upload_response.json()["uploadId"]

    delete_response = client.delete(f"/api/v1/waybill-uploads/{upload_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {
        "status": "deleted",
        "uploadId": upload_id,
    }

    list_response = client.get("/api/v1/waybill-uploads")
    assert list_response.status_code == 200
    assert list_response.json()["items"] == []

    actions = {
        row.action
        for row in db_session.execute(select(AuditLog)).scalars().all()
    }
    assert "delete_waybill_upload" in actions


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
        "/api/v1/waybill-uploads?status=pending_review"
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
