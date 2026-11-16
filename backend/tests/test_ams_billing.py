from decimal import Decimal

from sqlalchemy import select

from app.db.models import BillingEntry
from app.services.supplier_defaults import QLS_SUPPLIER_ID
from tests.auth_helpers import create_test_user, login
from tests.test_supplier_billing_flow import upload_data, upload_files, workbook_bytes


def test_ams_customer_weight_fee_estimate_upload_and_cancellation(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    login(client, email=admin.email)
    config = {"customerRates": [{"userId": str(customer.id), "rateEurPerKg": "0.75"}]}
    saved = client.put("/api/v1/billing/ams-settings", json={"config": config})
    assert saved.status_code == 200, saved.text
    assert saved.json()["config"] == config
    assert saved.json()["version"] == 1
    assert client.get("/api/v1/billing/ams-settings").json()["config"] == config

    login(client, email=customer.email)
    assert client.get("/api/v1/billing/ams-settings").status_code == 403
    content = workbook_bytes(["P1", "P2"])
    estimated = client.post(
        "/api/v1/billing/estimate",
        data={"supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS", "grossWeightKg": "12.5"},
        files={"preAlertFile": ("data.xlsx", content)},
    )
    assert estimated.status_code == 200, estimated.text
    assert estimated.json()["amsWeightRateEur"] == "0.75"
    assert estimated.json()["amsWeightFeeEur"] == "9.38"
    assert estimated.json()["estimatedTotal"] == "19.38"

    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(content))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["amsWeightFeeEur"] == "9.38"
    assert uploaded.json()["deductedTotal"] == "19.38"
    assert uploaded.json()["balanceAfter"] == "80.62"
    entries = {entry.fee_type: entry for entry in db_session.scalars(select(BillingEntry).where(BillingEntry.entry_type == "deduction")).all()}
    assert set(entries) == {"customs_tax", "declaration_operation_fee", "ams_weight_handling"}
    assert entries["ams_weight_handling"].amount == Decimal("9.38")
    assert entries["ams_weight_handling"].quantity == Decimal("12.5")
    assert entries["ams_weight_handling"].unit_rate == Decimal("0.75")
    assert entries["ams_weight_handling"].currency == "EUR"
    assert any(item["feeType"] == "ams_weight_handling" for item in client.get("/api/v1/billing/me/invoices/eligible").json())

    login(client, email=admin.email)
    approved = client.patch(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/status", json={"status": "approved"})
    assert approved.status_code == 200, approved.text
    tracking = client.get("/api/v1/waybills").json()["items"][0]
    detail = client.get(f"/api/v1/waybills/{tracking['publicCode']}").json()
    assert next(fee for fee in detail["billingFees"] if fee["feeType"] == "ams_weight_handling")["amount"] == "9.38"
    assert client.patch(f"/api/v1/waybills/{tracking['publicCode']}", json={"airportOfArrival": "FRA"}).status_code == 409
    cancelled = client.post(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/cancel", json={"reason": "test cancellation"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["refundedAmount"] == "19.38"
    assert cancelled.json()["record"]["amsWeightFeeAmountDeleted"] == "9.38"
    db_session.refresh(customer)
    assert customer.balance == Decimal("100.00")


def test_ams_fee_skips_unlisted_customers_and_other_airports(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    listed = create_test_user(db_session, email="listed@example.com", balance="100.00")
    other = create_test_user(db_session, email="other@example.com", balance="100.00")
    login(client, email=admin.email)
    assert client.put("/api/v1/billing/ams-settings", json={"config": {
        "customerRates": [{"userId": str(listed.id), "rateEurPerKg": "0.50"}]
    }}).status_code == 200
    content = workbook_bytes(["P1"])
    login(client, email=other.email)
    unlisted = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(content))
    assert unlisted.status_code == 201, unlisted.text
    assert unlisted.json()["amsWeightFeeEur"] == "0.00"
    assert unlisted.json()["deductedTotal"] == "5.00"

    login(client, email=listed.email)
    other_airport = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="FRA", number="784-84063277"), files=upload_files(content))
    assert other_airport.status_code == 201, other_airport.text
    assert other_airport.json()["amsWeightFeeEur"] == "0.00"
    assert other_airport.json()["deductedTotal"] == "2.00"
    assert not db_session.scalars(select(BillingEntry).where(BillingEntry.fee_type == "ams_weight_handling")).all()


def test_ams_settings_reject_duplicate_customers_and_invalid_price(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com")
    login(client, email=admin.email)
    rate = {"userId": str(customer.id), "rateEurPerKg": "0.50"}
    assert client.put("/api/v1/billing/ams-settings", json={"config": {"customerRates": [rate, rate]}}).status_code == 422
    assert client.put("/api/v1/billing/ams-settings", json={"config": {"customerRates": [{**rate, "rateEurPerKg": "0"}]}}).status_code == 422


def test_ams_fee_is_included_in_balance_check_before_upload(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="10.00")
    login(client, email=admin.email)
    assert client.put("/api/v1/billing/ams-settings", json={"config": {
        "customerRates": [{"userId": str(customer.id), "rateEurPerKg": "0.50"}]
    }}).status_code == 200
    login(client, email=customer.email)
    response = client.post(
        "/api/v1/waybill-uploads/file",
        data=upload_data(), files=upload_files(workbook_bytes(["P1"])),
    )
    assert response.status_code == 402, response.text
    assert "11.25" in response.text
    assert client.get("/api/v1/waybill-uploads").json()["items"] == []
    assert db_session.scalars(select(BillingEntry)).all() == []
