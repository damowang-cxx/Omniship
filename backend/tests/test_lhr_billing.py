from decimal import Decimal
import pytest
from pydantic import ValidationError

from sqlalchemy import select

from app.db.models import BillingEntry, WaybillUpload
from app.repositories.billing_repository import BillingRepository
from app.repositories.supplier_repository import SupplierRepository
from app.services.supplier_defaults import QLS_CONFIG, QLS_SUPPLIER_ID
from app.schemas.supplier import LhrBillingConfig
from app.services.lhr_billing import calculate_lhr_charges
from tests.auth_helpers import create_test_user, login
from tests.test_supplier_billing_flow import upload_data, upload_files, workbook_bytes
from tests.test_invoices_api import ready_settings


def configure_lhr(db_session, user, *, rate="0.50", surcharge_rules=None):
    repository = SupplierRepository(db_session)
    settings = repository.get_settings()
    settings.lhr_billing = {
        "clearanceFeeEur": "45.00",
        "customerRates": [{"userId": str(user.id), "rateGbpPerKg": rate}],
        "surchargeRules": surcharge_rules or [],
    }
    settings.lhr_billing_version += 1
    db_session.commit()


def test_lhr_estimate_upload_and_separate_wallets(client, db_session):
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("31.25")
    db_session.commit()
    configure_lhr(db_session, user, surcharge_rules=[{"name": "Menzies", "mode": "fixed", "prefixes": ["784"], "amountGbp": "25.00"}])
    login(client, email=user.email)
    content = workbook_bytes(["P1", "P2", "P3"])
    estimate = client.post(
        "/api/v1/billing/estimate",
        data={"supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "LHR", "grossWeightKg": "12.5", "airWaybillNumber": "784-84063276"},
        files={"preAlertFile": ("data.xlsx", content)},
    )
    assert estimate.status_code == 200, estimate.text
    assert {name: estimate.json()[name] for name in ("lhrClearanceEur", "lhrWeightFeeGbp", "estimatedTax", "estimatedOperationFee")} == {
        "lhrClearanceEur": "45.00", "lhrWeightFeeGbp": "6.25", "estimatedTax": "0.00", "estimatedOperationFee": "0.00",
    }
    assert estimate.json()["lhrTerminalSurchargeGbp"] == "25.00"
    assert estimate.json()["estimatedTotalGbp"] == "31.25"
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(content))
    assert response.status_code == 201, response.text
    assert response.json()["deductedTotal"] == "45.00"
    assert response.json()["balanceAfter"] == "0.00"
    assert response.json()["gbpBalanceAfter"] == "0.00"
    entries = {entry.fee_type: entry for entry in db_session.scalars(select(BillingEntry).where(BillingEntry.entry_type == "deduction")).all()}
    assert set(entries) == {"lhr_clearance", "lhr_weight_handling", "lhr_terminal_surcharge"}
    assert entries["lhr_clearance"].amount == Decimal("45.00")
    assert entries["lhr_weight_handling"].amount == Decimal("6.25")
    assert entries["lhr_weight_handling"].quantity == Decimal("12.5")
    assert entries["lhr_weight_handling"].currency == "GBP"
    assert entries["lhr_terminal_surcharge"].amount == Decimal("25.00")
    assert entries["lhr_terminal_surcharge"].fee_description.startswith("LHR 货站附加费 · Menzies · 784")
    assert entries["lhr_terminal_surcharge"].balance_after == Decimal("0.00")


def test_lhr_weight_bands_round_up_and_reject_duplicate_prefixes(db_session):
    user = create_test_user(db_session, email="lhr@example.com")
    rule = {"name": "Swissport", "mode": "weight_bands", "prefixes": ["016", "180"], "bands": [
        {"minWeightKg": 0, "maxWeightKg": 500, "amountGbp": "25.00"},
        {"minWeightKg": 501, "maxWeightKg": 1000, "amountGbp": "30.00"},
        {"minWeightKg": 1001, "maxWeightKg": None, "amountGbp": "35.00"},
    ]}
    payload = {"clearanceFeeEur": "45.00", "customerRates": [{"userId": str(user.id), "rateGbpPerKg": "0.50"}], "surchargeRules": [rule]}
    config = LhrBillingConfig.model_validate(payload)
    at_500 = calculate_lhr_charges(config=config, user_id=user.id, waybill_number="016-12345678", gross_weight_kg=Decimal("500"))
    at_500_5 = calculate_lhr_charges(config=config, user_id=user.id, waybill_number="180-12345678", gross_weight_kg=Decimal("500.5"))
    assert at_500.surcharge_gbp == Decimal("25.00")
    assert at_500_5.surcharge_gbp == Decimal("30.00")
    assert at_500_5.weight_fee_gbp == Decimal("250.25")
    with pytest.raises(ValidationError, match="prefix may appear in only one"):
        LhrBillingConfig.model_validate({**payload, "surchargeRules": [rule, {"name": "Other", "mode": "fixed", "prefixes": ["016"], "amountGbp": "21.00"}]})
    with pytest.raises(ValidationError, match="contiguous"):
        LhrBillingConfig.model_validate({**payload, "surchargeRules": [{**rule, "bands": [rule["bands"][0], {**rule["bands"][1], "minWeightKg": 502}, rule["bands"][2]]}]})


def test_admin_saves_one_global_lhr_schedule_without_changing_supplier_versions(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="lhr@example.com")
    login(client, email=admin.email)
    config = {
        "clearanceFeeEur": "48.00",
        "customerRates": [{"userId": str(customer.id), "rateGbpPerKg": "0.75"}],
        "surchargeRules": [{"name": "Menzies", "mode": "fixed", "prefixes": ["784", "205"], "amountGbp": "21.00"}],
    }
    response = client.put("/api/v1/billing/lhr-settings", json={"config": config})
    assert response.status_code == 200, response.text
    assert response.json()["version"] == 1
    assert response.json()["config"]["customerRates"][0]["rateGbpPerKg"] == "0.75"
    assert SupplierRepository(db_session).get(QLS_SUPPLIER_ID).current_version_number == 1
    config["surchargeRules"].append({"name": "Duplicate", "mode": "fixed", "prefixes": ["784"], "amountGbp": "25.00"})
    rejected = client.put("/api/v1/billing/lhr-settings", json={"config": config})
    assert rejected.status_code == 422
    assert client.get("/api/v1/billing/lhr-settings").json()["version"] == 1
    customer.balance = Decimal("48.00")
    customer.gbp_balance = Decimal("30.38")
    db_session.commit()
    login(client, email=customer.email)
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["lhrClearanceEur"] == "48.00"
    assert uploaded.json()["lhrWeightRateGbp"] == "0.75"
    assert uploaded.json()["lhrWeightFeeGbp"] == "9.38"
    assert uploaded.json()["lhrTerminalSurchargeGbp"] == "21.00"
    assert uploaded.json()["gbpBalanceAfter"] == "0.00"


def test_lhr_settings_are_admin_only_and_supplier_versions_cannot_set_them(client, db_session):
    user = create_test_user(db_session, email="user@example.com")
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    login(client, email=user.email)
    assert client.get("/api/v1/billing/lhr-settings").status_code == 403
    assert client.put("/api/v1/billing/lhr-settings", json={"config": None}).status_code == 403
    login(client, email=admin.email)
    assert client.get("/api/v1/billing/lhr-settings").json() == {"config": None, "version": 0}
    supplier_config = {**QLS_CONFIG, "lhrBilling": {
        "clearanceFeeEur": "45.00", "customerRates": [], "surchargeRules": [],
    }}
    rejected = client.post(f"/api/v1/suppliers/{QLS_SUPPLIER_ID}/versions", json={"config": supplier_config})
    assert rejected.status_code == 400
    assert "separate LHR billing settings" in rejected.json()["detail"]
    assert SupplierRepository(db_session).get(QLS_SUPPLIER_ID).current_version_number == 1


def test_lhr_gbp_shortfall_rolls_back_both_charges(client, db_session):
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("6.25")
    db_session.commit()
    configure_lhr(db_session, user, surcharge_rules=[{"name": "Menzies", "mode": "fixed", "prefixes": ["784"], "amountGbp": "25.00"}])
    login(client, email=user.email)
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(b"not an excel workbook"))
    assert response.status_code == 402
    assert response.json()["detail"]["currency"] == "GBP"
    assert response.json()["detail"]["required"] == "31.25"
    db_session.refresh(user)
    assert user.balance == Decimal("45.00")
    assert user.gbp_balance == Decimal("6.25")
    assert db_session.scalars(select(BillingEntry)).all() == []
    assert db_session.scalars(select(WaybillUpload)).all() == []


def test_lhr_customer_outside_fee_list_uploads_without_any_charge(client, db_session):
    configured = create_test_user(db_session, email="configured@example.com", balance="45.00")
    user = create_test_user(db_session, email="missing-rate@example.com", balance="0.00")
    db_session.commit()
    configure_lhr(db_session, configured, surcharge_rules=[{"name": "Menzies", "mode": "fixed", "prefixes": ["784"], "amountGbp": "25.00"}])
    login(client, email=user.email)
    estimate = client.post(
        "/api/v1/billing/estimate",
        data={"supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "LHR", "grossWeightKg": "12.5", "airWaybillNumber": "784-84063276"},
        files={"preAlertFile": ("data.xlsx", workbook_bytes([]))},
    )
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["lhrClearanceEur"] == "0.00"
    assert estimate.json()["lhrWeightRateGbp"] == "0.00"
    assert estimate.json()["estimatedTotalGbp"] == "0.00"
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    assert response.status_code == 201, response.text
    assert response.json()["deductedTotal"] == "0.00"
    assert response.json()["deductedTotalGbp"] == "0.00"
    db_session.refresh(user)
    assert user.balance == Decimal("0.00")
    assert user.gbp_balance == Decimal("0.00")
    assert db_session.scalars(select(BillingEntry)).all() == []
    assert len(db_session.scalars(select(WaybillUpload)).all()) == 1


def test_lhr_upload_without_global_fee_schedule_is_free(client, db_session):
    user = create_test_user(db_session, email="lhr@example.com", balance="0.00")
    login(client, email=user.email)
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    assert response.status_code == 201, response.text
    assert response.json()["lhrClearanceEur"] == "0.00"
    assert response.json()["deductedTotalGbp"] == "0.00"
    assert db_session.scalars(select(BillingEntry)).all() == []


def test_lhr_second_ledger_failure_rolls_back_eur_and_gbp(client, db_session, monkeypatch, tmp_path):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "upload_storage_dir", tmp_path)
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("10.00")
    db_session.commit()
    configure_lhr(db_session, user)
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
    configure_lhr(db_session, user)
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


def test_lhr_surcharge_refund_then_cancel_refunds_only_remaining_fees(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("40.00")
    db_session.commit()
    configure_lhr(db_session, user, surcharge_rules=[{"name": "Menzies", "mode": "fixed", "prefixes": ["784"], "amountGbp": "25.00"}])
    login(client, email=user.email)
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["gbpBalanceAfter"] == "8.75"
    login(client, email=admin.email)
    entries = client.get(f"/api/v1/billing/users/{user.id}").json()["deductions"]
    surcharge = next(entry for entry in entries if entry["feeType"] == "lhr_terminal_surcharge")
    refunded = client.post(f"/api/v1/billing/users/{user.id}/deductions/{surcharge['id']}/cancel")
    assert refunded.status_code == 200, refunded.text
    assert refunded.json()["user"]["gbpBalance"] == "33.75"
    cancelled = client.post(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/cancel", json={"reason": "test"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["refundedAmount"] == "45.00"
    assert cancelled.json()["gbpRefundedAmount"] == "6.25"
    assert cancelled.json()["record"]["lhrTerminalSurchargeAmountDeleted"] == "25.00"
    db_session.refresh(user)
    assert user.balance == Decimal("45.00")
    assert user.gbp_balance == Decimal("40.00")


def test_lhr_fees_create_separate_currency_invoices(client, db_session, tmp_path):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    user = create_test_user(db_session, email="lhr@example.com", balance="45.00")
    user.gbp_balance = Decimal("40.00")
    user.payer_company_name = "LHR Customer"
    user.payer_address_info = "London"
    ready_settings(db_session, tmp_path, admin)
    db_session.commit()
    configure_lhr(db_session, user, surcharge_rules=[{"name": "Menzies", "mode": "fixed", "prefixes": ["784"], "amountGbp": "25.00"}])
    login(client, email=user.email)
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport="LHR"), files=upload_files(workbook_bytes([])))
    assert uploaded.status_code == 201, uploaded.text
    eligible = client.get("/api/v1/billing/me/invoices/eligible")
    assert eligible.status_code == 200, eligible.text
    by_type = {entry["feeType"]: entry for entry in eligible.json()}
    assert set(by_type) == {"lhr_clearance", "lhr_weight_handling", "lhr_terminal_surcharge"}
    assert by_type["lhr_clearance"]["currency"] == "EUR"
    assert by_type["lhr_weight_handling"]["currency"] == "GBP"
    assert by_type["lhr_weight_handling"]["quantity"] == 12.5
    assert by_type["lhr_weight_handling"]["unitRate"] == "0.50"
    assert by_type["lhr_terminal_surcharge"]["currency"] == "GBP"
    assert by_type["lhr_terminal_surcharge"]["unitRate"] == "25.00"
    assert by_type["lhr_terminal_surcharge"]["feeName"].startswith("LHR 货站附加费 · Menzies")
    created = client.post("/api/v1/billing/me/invoices", json={"deductionIds": [entry["id"] for entry in eligible.json()], "issuedDate": "2026-11-04"})
    assert created.status_code == 201, created.text
    invoices = {invoice["currency"]: invoice for invoice in created.json()["invoices"]}
    assert set(invoices) == {"EUR", "GBP"}
    assert invoices["EUR"]["totalAmount"] == "45.00"
    assert invoices["GBP"]["totalAmount"] == "31.25"
    assert client.get("/api/v1/billing/me/invoices/eligible").json() == []
