from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill
from sqlalchemy import select

from app.db.models import BillingEntry, WaybillUpload
from app.repositories.billing_repository import BillingRepository
from app.repositories.waybill_upload_repository import WaybillUploadRepository
from app.schemas.supplier import SupplierVersionConfig
from app.services.operation_fee import OPERATION_FEE_TYPE, count_operation_rows
from app.services.supplier_defaults import QLS_SUPPLIER_ID, QLS_VERSION_ID
from app.services.waybill_service import WaybillService
from tests.auth_helpers import create_test_user, login
from tests.test_invoices_api import ready_settings
from tests.test_supplier_billing_flow import (
    grouped_billing_config, upload_data, upload_files, workbook_bytes,
)


def legacy_upload(db, user, tmp_path, content=None):
    """An old approved upload with no fee records, created without the new uploader."""
    repo = WaybillUploadRepository(db)
    upload = repo.create(
        user_id=user.id, uploaded_by_user_id=user.id,
        supplier_id=QLS_SUPPLIER_ID, supplier_version_id=QLS_VERSION_ID,
        shipment_type="Air", air_waybill_number="784-LEGACY", gross_weight_kg=Decimal("10"),
        pieces=3, arrival_flight_number=None, airport_of_departure="HKG", airport_of_arrival="FRA",
        validation_issue_count=0, validation_issues=[],
    )
    upload.status = "approved"
    upload.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    content = content if content is not None else workbook_bytes(["P1", "P1", "P2"])
    path = tmp_path / "legacy.xlsx"
    path.write_bytes(content)
    repo.add_file(upload_id=upload.id, file_kind="customer_pre_alert", original_filename=path.name,
                  storage_path=str(path), content_type=None, size_bytes=len(content), sha256="0" * 64)
    tracking = WaybillService(db).ensure_tracking_for_upload(upload)
    db.commit()
    return upload, tracking.public_code


def test_physical_rows_ignore_billing_filters_and_count_formulas():
    workbook = Workbook()
    workbook.active.title = "Instructions"
    workbook.active.append(["Do not count this sheet"])
    sheet = workbook.create_sheet("Data")
    sheet.append(["Title"])
    for value in ["same", "same", None, "   ", 0, '=IF(1=1,"","")', "invalid"]:
        sheet.append([value])
    sheet.cell(50, 1).fill = PatternFill("solid", fgColor="FF0000")
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    config = grouped_billing_config()
    config["workbook"].update(sheetMode="named", sheetName="Data", headerRow=3, dataStartRow=7)
    assert count_operation_rows(filename="rows.xlsx", content=output.getvalue(), config=SupplierVersionConfig.model_validate(config)) == 5
    config["workbook"]["sheetName"] = "Missing"
    with pytest.raises(ValueError, match="Missing"):
        count_operation_rows(filename="rows.xlsx", content=output.getvalue(), config=SupplierVersionConfig.model_validate(config))


def test_xls_rows_include_empty_formula_and_skip_formatted_blank():
    config = grouped_billing_config()
    config["workbook"].update(sheetMode="named", sheetName="Data")
    assert count_operation_rows(
        filename="rows.xls", content=(Path(__file__).parent / "fixtures" / "operation_rows.xls").read_bytes(),
        config=SupplierVersionConfig.model_validate(config),
    ) == 5


def test_estimate_and_upload_match_two_fees(client, db_session):
    user = create_test_user(db_session, email="fee@example.com", balance="26.00")
    login(client, email=user.email)
    content = workbook_bytes(["P1"] * 5 + ["P2"] * 5)
    estimate = client.post("/api/v1/billing/estimate", data={"supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS"},
                           files={"preAlertFile": ("data.xlsx", content)})
    assert estimate.status_code == 200
    assert {key: estimate.json()[key] for key in ("estimatedTax", "estimatedOperationFee", "estimatedTotal")} == {
        "estimatedTax": "6.00", "estimatedOperationFee": "20.00", "estimatedTotal": "26.00",
    }
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(content))
    assert response.status_code == 201
    assert response.json()["balanceAfter"] == "0.00"
    entries = {entry.fee_type: entry for entry in db_session.scalars(select(BillingEntry)).all()}
    assert entries["customs_tax"].balance_after == Decimal("20.00")
    assert entries[OPERATION_FEE_TYPE].amount == Decimal("20.00")
    assert entries[OPERATION_FEE_TYPE].balance_after == Decimal("0.00")


def test_upload_rolls_back_both_fees_and_files(client, db_session, monkeypatch, tmp_path):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "upload_storage_dir", tmp_path)
    user = create_test_user(db_session, email="fee@example.com", balance="30.00")
    login(client, email=user.email)
    original = BillingRepository.create_deduction

    def fail_second(self, **kwargs):
        if kwargs.get("fee_type") == OPERATION_FEE_TYPE:
            raise RuntimeError("injected operation fee write failure")
        return original(self, **kwargs)

    monkeypatch.setattr(BillingRepository, "create_deduction", fail_second)
    with pytest.raises(RuntimeError, match="injected"):
        client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(workbook_bytes(["P1"])))
    db_session.refresh(user)
    assert user.balance == Decimal("30.00")
    assert db_session.scalars(select(BillingEntry)).all() == []
    assert db_session.scalars(select(WaybillUpload)).all() == []
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


def test_legacy_backfill_permission_balance_reversal_and_retry(client, db_session, tmp_path):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    user = create_test_user(db_session, email="fee@example.com", balance="5.00")
    upload, code = legacy_upload(db_session, user, tmp_path)
    upload.supplier.status = "inactive"
    db_session.commit()
    endpoint = f"/api/v1/waybills/{code}/operation-fee/backfill"
    login(client, email=user.email)
    assert client.get(f"/api/v1/waybills/{code}").json()["canBackfillOperationFee"] is False
    assert client.post(endpoint).status_code == 403
    login(client, email=admin.email)
    assert client.get(f"/api/v1/waybills/{code}").json()["canBackfillOperationFee"] is True
    assert client.post(endpoint).status_code == 400
    db_session.refresh(user)
    assert user.balance == Decimal("5.00")
    assert db_session.scalars(select(BillingEntry)).all() == []
    user.balance = Decimal("20.00")
    db_session.commit()
    result = client.post(endpoint)
    assert result.status_code == 200, result.text
    assert result.json()["operationFeeStatus"] == "paid"
    assert result.json()["canBackfillOperationFee"] is False
    assert result.json()["billingBalance"] == "14.00"
    fee = result.json()["billingFees"][0]
    assert fee["quantity"] == 3
    assert fee["amount"] == "6.00"
    assert client.post(endpoint).status_code == 409
    reversed_result = client.post(f"/api/v1/billing/users/{user.id}/deductions/{fee['entryId']}/cancel")
    assert reversed_result.status_code == 200
    assert reversed_result.json()["user"]["balance"] == "20.00"
    assert {entry["feeType"] for entry in reversed_result.json()["deductions"]} == {OPERATION_FEE_TYPE}
    detail = client.get(f"/api/v1/waybills/{code}").json()
    assert detail["operationFeeStatus"] == "reversed"
    assert detail["canBackfillOperationFee"] is False
    assert client.post(endpoint).status_code == 409
    assert client.post(f"/api/v1/billing/users/{user.id}/deductions/{fee['entryId']}/cancel").status_code == 409
    cancelled = client.post(f"/api/v1/waybill-uploads/{upload.id}/cancel", json={"reason": "remove old upload"})
    assert cancelled.status_code == 200
    assert cancelled.json()["refundedAmount"] == "0.00"
    assert cancelled.json()["record"]["operationFeeAmountDeleted"] == "6.00"


@pytest.mark.parametrize("problem", ["missing", "invalid", "empty", "missing_sheet"])
def test_backfill_invalid_file_is_atomic(client, db_session, tmp_path, problem):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    user = create_test_user(db_session, email="fee@example.com", balance="20.00")
    upload, code = legacy_upload(db_session, user, tmp_path)
    path = Path(upload.files[0].storage_path)
    if problem == "missing":
        path.unlink()
    elif problem == "invalid":
        path.write_bytes(b"invalid workbook")
    elif problem == "empty":
        path.write_bytes(workbook_bytes([]))
    else:
        config = dict(upload.supplier_version.config)
        config["workbook"] = {**config["workbook"], "sheetMode": "named", "sheetName": "Missing"}
        upload.supplier_version.config = config
        db_session.commit()
    login(client, email=admin.email)
    assert client.post(f"/api/v1/waybills/{code}/operation-fee/backfill").status_code == 400
    db_session.refresh(user)
    assert user.balance == Decimal("20.00")
    assert db_session.scalars(select(BillingEntry)).all() == []


def test_invoice_keeps_operation_fee_separate_and_extra_fees_once(client, db_session, tmp_path):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    user = create_test_user(db_session, email="fee@example.com")
    user.payer_company_name = "Customer"
    user.payer_address_info = "Address"
    ready_settings(db_session, tmp_path, admin)
    db_session.commit()
    login(client, email=user.email)
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(workbook_bytes(["P1", "P1"])))
    assert uploaded.status_code == 201
    upload_id = uploaded.json()["uploadId"]
    login(client, email=admin.email)
    assert client.patch(f"/api/v1/waybill-uploads/{upload_id}/status", json={"status": "approved"}).status_code == 200
    code = client.get("/api/v1/waybills").json()["items"][0]["publicCode"]
    extra = client.post("/api/v1/waybills/extra-fee-types", json={"name": "Truck"}).json()
    assert client.patch(f"/api/v1/waybills/{code}/extra-fees", json={"items": [{"feeTypeId": extra["id"], "amount": "12.50"}]}).status_code == 200
    login(client, email=user.email)
    eligible = client.get("/api/v1/billing/me/invoices/eligible").json()
    fees = {entry["feeType"]: entry for entry in eligible}
    assert fees[OPERATION_FEE_TYPE]["extraFeeTotal"] == "0.00"
    assert fees["customs_tax"]["extraFeeTotal"] == "12.50"
    created = client.post("/api/v1/billing/me/invoices", json={"deductionIds": [entry["id"] for entry in eligible], "issuedDate": "2026-11-04"})
    assert created.status_code == 201
    invoice = created.json()["invoices"][0]
    assert invoice["totalAmount"] == "19.50"
    assert {line["feeName"] for line in invoice["lines"]} == {"Customs tax", "申报行操作费"}
    assert client.get("/api/v1/billing/me/invoices/eligible").json() == []
    assert client.post("/api/v1/billing/me/invoices", json={"deductionIds": [entry["id"] for entry in eligible], "issuedDate": "2026-11-04"}).status_code == 409
    exported = client.get(f"/api/v1/billing/me/invoices/download?invoiceIds={invoice['id']}")
    workbook = load_workbook(BytesIO(exported.content))
    assert "申报行操作费" in " ".join(str(workbook.active.cell(row, 1).value) for row in (13, 14))
    workbook.close()
    login(client, email=admin.email)
    balance = db_session.get(type(user), user.id).balance
    assert client.post(f"/api/v1/waybill-uploads/{upload_id}/cancel", json={"reason": "has invoice"}).status_code == 409
    db_session.refresh(user)
    assert user.balance == balance
