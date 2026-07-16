from io import BytesIO

from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import AuditLog, BillingEntry
from tests.auth_helpers import create_test_user, login
from app.services.supplier_defaults import QLS_SUPPLIER_ID


def pre_alert_estimate_workbook() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append([f"Column {index}" for index in range(1, 24)])
    for parcel_number, destination in (
        ("P-DE", "DE"),
        ("P-FR", "France"),
        ("P-CH", "Switzerland"),
    ):
        row = [""] * 23
        row[8] = parcel_number
        row[18] = destination
        row[20] = 1
        row[21] = 0.5
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_admin_recharges_user_and_receipt_is_private(client, db_session, tmp_path):
    settings = get_settings()
    original_storage_dir = settings.billing_receipt_storage_dir
    settings.billing_receipt_storage_dir = tmp_path / "billing-receipts"
    try:
        admin = create_test_user(
            db_session,
            email="admin@example.com",
            username="Admin",
            role="admin",
        )
        user = create_test_user(
            db_session, email="user@example.com", username="User", balance="0.00"
        )
        assert login(client, email=admin.email).status_code == 200

        initial_users = client.get("/api/v1/users")
        listed_user = next(
            item for item in initial_users.json()["items"] if item["id"] == str(user.id)
        )
        assert listed_user["balance"] == "0.00"

        png_content = b"\x89PNG\r\n\x1a\nreceipt-image"
        recharge_response = client.post(
            f"/api/v1/billing/users/{user.id}/recharges",
            data={"amount": "25.50"},
            files={"receipt": ("payment.png", png_content, "image/png")},
        )
        assert recharge_response.status_code == 200
        body = recharge_response.json()
        assert body["user"]["balance"] == "25.50"
        assert body["deductions"] == []
        assert body["recharges"][0]["amount"] == "25.50"
        assert body["recharges"][0]["balanceAfter"] == "25.50"
        assert body["recharges"][0]["receipt"]["originalFilename"] == "payment.png"

        entry_id = body["recharges"][0]["id"]
        receipt_response = client.get(
            f"/api/v1/billing/users/{user.id}/recharges/{entry_id}/receipt"
        )
        assert receipt_response.status_code == 200
        assert receipt_response.content == png_content

        assert login(client, email=user.email).status_code == 200
        account_response = client.get("/api/v1/billing/me")
        assert account_response.status_code == 200
        assert account_response.json()["user"]["balance"] == "25.50"
        forbidden_recharge = client.post(
            f"/api/v1/billing/users/{user.id}/recharges",
            data={"amount": "10"},
        )
        assert forbidden_recharge.status_code == 403

        entry = db_session.execute(select(BillingEntry)).scalar_one()
        assert str(entry.amount) == "25.50"
        actions = {
            row.action for row in db_session.execute(select(AuditLog)).scalars().all()
        }
        assert "recharge_user" in actions
        assert "download_recharge_receipt" in actions
    finally:
        settings.billing_receipt_storage_dir = original_storage_dir


def test_recharge_validates_amount_and_image(client, db_session):
    admin = create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    user = create_test_user(
        db_session, email="user@example.com", username="User", balance="0.00"
    )
    assert login(client, email=admin.email).status_code == 200

    invalid_amount = client.post(
        f"/api/v1/billing/users/{user.id}/recharges",
        data={"amount": "0"},
    )
    assert invalid_amount.status_code == 400
    assert "greater than zero" in invalid_amount.text

    invalid_image = client.post(
        f"/api/v1/billing/users/{user.id}/recharges",
        data={"amount": "10"},
        files={"receipt": ("payment.png", b"not-an-image", "image/png")},
    )
    assert invalid_image.status_code == 400
    assert "valid image" in invalid_image.text


def test_estimates_three_euros_for_each_eu_shipment(client, db_session):
    user = create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email=user.email).status_code == 200

    response = client.post(
        "/api/v1/billing/estimate",
        data={
            "supplierId": str(QLS_SUPPLIER_ID),
            "airportOfArrival": "AMS",
        },
        files={
            "preAlertFile": (
                "pre-alert.xlsx",
                pre_alert_estimate_workbook(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "supplierId": str(QLS_SUPPLIER_ID),
        "supplierName": "QLS",
        "supplierVersionId": "00000000-0000-0000-0000-000000000502",
        "supplierVersionNumber": 1,
        "taxableAirport": True,
        "billableUnitCount": 3,
        "unitRate": "3.00",
        "estimatedTax": "9.00",
        "warningCount": 0,
        "warnings": [],
        "currency": "EUR",
    }
