from decimal import Decimal

from sqlalchemy import select

from app.db.models import BillingEntry, WaybillUpload
from app.repositories.billing_repository import BillingRepository
from app.services.supplier_defaults import QLS_SUPPLIER_ID
from tests.auth_helpers import create_test_user, login
from tests.test_supplier_billing_flow import upload_data, upload_files, workbook_bytes
from tests.test_invoices_api import ready_settings


def test_lhr_estimate_upload_and_separate_wallets(client, db_session):
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("6.25")
    db_session.commit()
    login(client, email=user.email)
    content = workbook_bytes(["P1", "P2", "P3"])
    estimate = client.post(
        "/api/v1/billing/estimate",
        data={"supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "LHR", "grossWeightKg": "12.5"},
        files={"preAlertFile": ("data.xlsx", content)},
    )
    assert estimate.status_code == 200, estimate.text
    assert {name: estimate.json()[name] for name in ("lhrClearanceEur", "lhrWeightFeeGbp", "estimatedTax", "estimatedOperationFee")} == {
        "lhrClearanceEur": "45.00", "lhrWeightFeeGbp": "6.25", "estimatedTax": "0.00", "estimatedOperationFee": "0.00",
    }
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(content))
    assert response.status_code == 201, response.text
    assert response.json()["deductedTotal"] == "45.00"
    assert response.json()["balanceAfter"] == "0.00"
    assert response.json()["gbpBalanceAfter"] == "0.00"
    entries = {entry.fee_type: entry for entry in db_session.scalars(select(BillingEntry).where(BillingEntry.entry_type == "deduction")).all()}
    assert set(entries) == {"lhr_clearance", "lhr_weight_handling"}
    assert entries["lhr_clearance"].amount == Decimal("45.00")
    assert entries["lhr_weight_handling"].amount == Decimal("6.25")
    assert entries["lhr_weight_handling"].quantity == Decimal("12.5")
    assert entries["lhr_weight_handling"].currency == "GBP"


def test_lhr_gbp_shortfall_rolls_back_both_charges(client, db_session):
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    login(client, email=user.email)
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(b"not an excel workbook"))
    assert response.status_code == 402
    assert response.json()["detail"]["currency"] == "GBP"
    db_session.refresh(user)
    assert user.balance == Decimal("45.00")
    assert user.gbp_balance == Decimal("0.00")
    assert db_session.scalars(select(BillingEntry)).all() == []
    assert db_session.scalars(select(WaybillUpload)).all() == []


def test_lhr_second_ledger_failure_rolls_back_eur_and_gbp(client, db_session, monkeypatch, tmp_path):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("10.00")
    db_session.commit()
    login(client, email=user.email)
    original = BillingRepository.create_deduction

    def fail_gbp(self, **kwargs):
        if kwargs.get("fee_type") == "lhr_weight_handling":
            raise RuntimeError("injected GBP ledger failure")
        return original(self, **kwargs)

    monkeypatch.setattr(BillingRepository, "create_deduction", fail_gbp)
    import pytest
    with pytest.raises(RuntimeError, match="injected"):
        client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    db_session.refresh(user)
    assert user.balance == Decimal("45.00")
    assert user.gbp_balance == Decimal("10.00")
    assert db_session.scalars(select(BillingEntry)).all() == []
    assert db_session.scalars(select(WaybillUpload)).all() == []
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_admin_gbp_recharge_and_lhr_refund(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    login(client, email=admin.email)
    recharge = client.post(f"/api/v1/billing/users/{user.id}/recharges", data={"amount": "10.00", "currency": "GBP"})
    assert recharge.status_code == 200, recharge.text
    assert recharge.json()["user"]["gbpBalance"] == "10.00"
    login(client, email=user.email)
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["gbpBalanceAfter"] == "3.75"
    login(client, email=admin.email)
    entries = client.get(f"/api/v1/billing/users/{user.id}").json()["deductions"]
    gbp_entry = next(entry for entry in entries if entry["feeType"] == "lhr_weight_handling")
    refunded = client.post(f"/api/v1/billing/users/{user.id}/deductions/{gbp_entry['id']}/cancel")
    assert refunded.status_code == 200, refunded.text
    assert refunded.json()["user"]["gbpBalance"] == "10.00"
    assert refunded.json()["user"]["balance"] == "0.00"
    cancelled = client.post(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/cancel", json={"reason": "test"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["refundedAmount"] == "45.00"
    assert cancelled.json()["gbpRefundedAmount"] == "0.00"
    assert cancelled.json()["record"]["lhrClearanceAmountDeleted"] == "45.00"
    assert cancelled.json()["record"]["gbpFeeAmountDeleted"] == "6.25"


def test_lhr_fees_create_separate_currency_invoices(client, db_session, tmp_path):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("10.00")
    user.payer_company_name = "LHR Customer"
    user.payer_address_info = "London"
    ready_settings(db_session, tmp_path, admin)
    db_session.commit()
    login(client, email=user.email)
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    assert uploaded.status_code == 201, uploaded.text
    eligible = client.get("/api/v1/billing/me/invoices/eligible")
    assert eligible.status_code == 200, eligible.text
    by_currency = {entry["currency"]: entry for entry in eligible.json()}
    assert set(by_currency) == {"EUR", "GBP"}
    assert by_currency["EUR"]["feeType"] == "lhr_clearance"
    assert by_currency["GBP"]["feeType"] == "lhr_weight_handling"
    assert by_currency["GBP"]["quantity"] == 12.5
    assert by_currency["GBP"]["unitRate"] == "0.50"
    created = client.post("/api/v1/billing/me/invoices", json={"deductionIds": [entry["id"] for entry in eligible.json()], "issuedDate": "2026-11-04"})
    assert created.status_code == 201, created.text
    invoices = {invoice["currency"]: invoice for invoice in created.json()["invoices"]}
    assert set(invoices) == {"EUR", "GBP"}
    assert invoices["EUR"]["totalAmount"] == "45.00"
    assert invoices["GBP"]["totalAmount"] == "6.25"
    assert client.get("/api/v1/billing/me/invoices/eligible").json() == []
