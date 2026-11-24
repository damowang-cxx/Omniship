from copy import deepcopy
from decimal import Decimal
from io import BytesIO
from uuid import UUID

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.db.models import BillingEntry, BillingSettings, WaybillUpload
from app.schemas.supplier import AmsChargeItem
from app.services.ams_billing import calculate_ams_weight_difference
from app.services.supplier_defaults import QLS_CONFIG, QLS_SUPPLIER_ID
from tests.auth_helpers import create_test_user, login
from tests.test_supplier_billing_flow import upload_data, upload_files


def ams_config(customer_id, *, match_column="E", weight_column="V"):
    return {
        "matchColumn": match_column,
        "matchHeader": "NETWORK", "weightColumn": weight_column,
        "matchValues": ["DE-DHL", "Colissimo"],
        "customerRates": [{"userId": str(customer_id), "fees": [
            {"matchValue": "DE-DHL", "rateEurPerKg": "0.75"},
            {"matchValue": "Colissimo", "rateEurPerKg": "1.20"},
        ]}],
    }


def workbook(rows, *, match_index=4, weight_index=21, header="NETWORK", named=False):
    book = Workbook()
    sheet = book.active
    if named:
        sheet.title = "Shipments"
        sheet.append(["Instructions"])
        sheet.append(["Export"])
    titles = [f"Column {index}" for index in range(1, 24)]
    titles[match_index] = header
    sheet.append(titles)
    for index, (network, weight) in enumerate(rows):
        row = [None] * 23
        row[8], row[18], row[20], row[21] = f"P{index}", "DE", 1, 0.5
        row[match_index], row[weight_index] = network, weight
        sheet.append(row)
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


def publish(client, config, supplier_id=QLS_SUPPLIER_ID):
    suppliers = client.get("/api/v1/suppliers").json()["items"]
    template = deepcopy(next(item for item in suppliers if item["id"] == str(supplier_id))["currentVersion"]["config"])
    template["amsBilling"] = config
    response = client.post(f"/api/v1/suppliers/{supplier_id}/versions", json={"config": template})
    assert response.status_code == 200, response.text
    return response.json()


def test_template_ams_matches_multiple_channels_and_keeps_charge_snapshots(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    login(client, email=admin.email)
    config = ams_config(customer.id)
    published = publish(client, config)
    assert published["currentVersion"]["config"]["amsBilling"] == config
    old_settings = db_session.get(BillingSettings, 1)
    old_settings.ams_billing = {"taxHandlingFeeEur": "99.00", "customerRates": [
        {"userId": str(customer.id), "rateEurPerKg": "99.00"}
    ]}
    db_session.commit()

    login(client, email=customer.email)
    content = workbook([("DE-DHL", "1,25"), (" DE-DHL ", 2.75), ("Colissimo", 3.5), ("Other", 10)])
    estimate = client.post("/api/v1/billing/estimate", data={
        "supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS", "grossWeightKg": "7.5"
    }, files={"preAlertFile": ("data.xlsx", content)})
    assert estimate.status_code == 200, estimate.text
    charges = estimate.json()["amsCharges"]
    assert charges == [
        {"feeDescription": "DE-DHL", "quantity": "4.000", "unitRate": "0.75", "amount": "3.00"},
        {"feeDescription": "Colissimo", "quantity": "3.500", "unitRate": "1.20", "amount": "4.20"},
    ]
    assert estimate.json()["amsWeightFeeEur"] == "7.20"
    assert estimate.json()["amsWeightDifferenceKg"] == "0.000"
    assert estimate.json()["amsWeightDifferenceFeeEur"] == "0.00"
    assert estimate.json()["amsTaxHandlingFeeEur"] == "8.00"
    assert estimate.json()["estimatedTotal"] == "35.20"
    lower_gross = client.post("/api/v1/billing/estimate", data={
        "supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS", "grossWeightKg": "7.0",
    }, files={"preAlertFile": ("data.xlsx", content)})
    assert lower_gross.status_code == 200, lower_gross.text
    assert lower_gross.json()["amsWeightDifferenceFeeEur"] == "0.00"

    upload_payload = upload_data()
    upload_payload["grossWeightKg"] = "7.5"
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_payload, files=upload_files(content))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["amsCharges"] == charges
    assert uploaded.json()["amsWeightDifferenceFeeEur"] == "0.00"
    assert uploaded.json()["deductedTotal"] == "35.20"
    assert uploaded.json()["balanceAfter"] == "64.80"
    weights = db_session.scalars(select(BillingEntry).where(BillingEntry.fee_type == "ams_weight_handling")).all()
    assert {entry.fee_description: entry.amount for entry in weights} == {"DE-DHL": Decimal("3.00"), "Colissimo": Decimal("4.20")}
    eligible = client.get("/api/v1/billing/me/invoices/eligible").json()
    assert {entry["feeName"] for entry in eligible if entry["feeType"] == "ams_weight_handling"} == {"DE-DHL", "Colissimo"}

    login(client, email=admin.email)
    config["customerRates"][0]["fees"][0]["rateEurPerKg"] = "9.00"
    publish(client, config)
    assert client.patch(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/status", json={"status": "approved"}).status_code == 200
    tracking = client.get("/api/v1/waybills").json()["items"][0]
    detail = client.get(f"/api/v1/waybills/{tracking['publicCode']}").json()
    assert len([fee for fee in detail["billingFees"] if fee["feeType"] == "ams_weight_handling"]) == 2
    assert next(fee for fee in detail["billingFees"] if fee["feeDescription"] == "DE-DHL")["unitRate"] == "0.75"
    cancelled = client.post(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/cancel", json={"reason": "test"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["refundedAmount"] == "35.20"
    assert cancelled.json()["record"]["amsWeightFeeAmountDeleted"] == "7.20"
    db_session.refresh(customer)
    assert customer.balance == Decimal("100.00")


def test_gross_weight_difference_is_apportioned_by_excel_weight_and_refunded(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="2000.00")
    config = ams_config(customer.id, weight_column="Q")
    config["matchValues"] = ["DHL PAKET", "COLISSIMO", "NL DHL"]
    config["customerRates"][0]["fees"] = [
        {"matchValue": "DHL PAKET", "rateEurPerKg": "0.75"},
        {"matchValue": "COLISSIMO", "rateEurPerKg": "1.20"},
        {"matchValue": "NL DHL", "rateEurPerKg": "1.50"},
    ]
    login(client, email=admin.email)
    publish(client, config)
    login(client, email=customer.email)
    content = workbook([
        ("DHL PAKET", "817.808"), ("COLISSIMO", "23.533"), ("NL DHL", "25.635"),
    ], weight_index=16)
    estimate = client.post("/api/v1/billing/estimate", data={
        "supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS", "grossWeightKg": "905",
    }, files={"preAlertFile": ("data.xlsx", content)})
    assert estimate.status_code == 200, estimate.text
    estimated = estimate.json()
    assert estimated["amsWeightDifferenceKg"] == "38.024"
    assert estimated["amsWeightDifferenceCharges"] == [
        {"feeDescription": "DHL PAKET", "quantity": "35.868", "unitRate": "0.75", "amount": "26.90"},
        {"feeDescription": "COLISSIMO", "quantity": "1.032", "unitRate": "1.20", "amount": "1.24"},
        {"feeDescription": "NL DHL", "quantity": "1.124", "unitRate": "1.50", "amount": "1.69"},
    ]
    assert estimated["amsWeightDifferenceFeeEur"] == "29.83"
    assert Decimal(estimated["amsCharges"][1]["quantity"]) + Decimal(estimated["amsWeightDifferenceCharges"][1]["quantity"]) == Decimal("24.565")
    assert sum((Decimal(item["quantity"]) for item in estimated["amsCharges"] + estimated["amsWeightDifferenceCharges"]), Decimal("0")) == Decimal("905.000")

    upload_payload = upload_data()
    upload_payload["grossWeightKg"] = "905"
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_payload, files=upload_files(content))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["amsWeightDifferenceKg"] == estimated["amsWeightDifferenceKg"]
    assert uploaded.json()["amsWeightDifferenceCharges"] == estimated["amsWeightDifferenceCharges"]
    assert uploaded.json()["amsWeightDifferenceFeeEur"] == "29.83"
    assert uploaded.json()["deductedTotal"] == estimated["estimatedTotal"]
    entries = db_session.scalars(select(BillingEntry).where(
        BillingEntry.waybill_upload_id == UUID(uploaded.json()["uploadId"]),
        BillingEntry.fee_description == "清关费重量差异补收",
    )).all()
    assert len(entries) == 1
    assert entries[0].amount == Decimal("29.83")
    assert entries[0].fee_type == "ams_weight_handling"
    assert entries[0].quantity == Decimal("1") and entries[0].unit_rate == Decimal("29.83")
    eligible = client.get("/api/v1/billing/me/invoices/eligible").json()
    assert any(item["feeName"] == "清关费重量差异补收" and item["amount"] == "29.83" for item in eligible)

    login(client, email=admin.email)
    cancelled = client.post(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/cancel", json={"reason": "test"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["refundedAmount"] == uploaded.json()["deductedTotal"]
    assert cancelled.json()["record"]["amsWeightFeeAmountDeleted"] == "709.88"
    db_session.refresh(customer)
    assert customer.balance == Decimal("2000.00")


def test_weighted_difference_rounding_preserves_gross_weight():
    charges = [
        AmsChargeItem(feeDescription="A", quantity=Decimal("1.000"), unitRate=Decimal("1.00"), amount=Decimal("1.00")),
        AmsChargeItem(feeDescription="B", quantity=Decimal("1.000"), unitRate=Decimal("2.00"), amount=Decimal("2.00")),
    ]
    result = calculate_ams_weight_difference(charges, Decimal("2.001"))
    assert [item.quantity for item in result.charges] == [Decimal("0.001"), Decimal("0.000")]
    assert sum((item.quantity for item in charges + result.charges), Decimal("0")) == Decimal("2.001")


def test_same_template_and_details_use_each_customers_prices_for_estimate_and_deduction(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    first = create_test_user(db_session, email="first@example.com", balance="100.00")
    second = create_test_user(db_session, email="second@example.com", balance="100.00")
    config = ams_config(first.id)
    second_rate = ams_config(second.id)["customerRates"][0]
    second_rate["fees"][0]["rateEurPerKg"] = "1.50"
    second_rate["fees"][1]["rateEurPerKg"] = "0.80"
    config["customerRates"].append(second_rate)
    login(client, email=admin.email)
    assert publish(client, config)["currentVersion"]["config"]["amsBilling"] == config
    content = workbook([("DE-DHL", 1.25), ("DE-DHL", 2.75), ("Colissimo", 3.5)])
    expected = [
        [
            {"feeDescription": "DE-DHL", "quantity": "4.000", "unitRate": "0.75", "amount": "3.00"},
            {"feeDescription": "Colissimo", "quantity": "3.500", "unitRate": "1.20", "amount": "4.20"},
        ],
        [
            {"feeDescription": "DE-DHL", "quantity": "4.000", "unitRate": "1.50", "amount": "6.00"},
            {"feeDescription": "Colissimo", "quantity": "3.500", "unitRate": "0.80", "amount": "2.80"},
        ],
    ]
    for index, customer in enumerate((first, second)):
        login(client, email=customer.email)
        estimate = client.post("/api/v1/billing/estimate", data={
            "supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS", "grossWeightKg": "7.5",
        }, files={"preAlertFile": ("data.xlsx", content)})
        assert estimate.status_code == 200, estimate.text
        assert estimate.json()["amsCharges"] == expected[index]
        upload_payload = upload_data(number=f"784-8406327{index}")
        upload_payload["grossWeightKg"] = "7.5"
        uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_payload, files=upload_files(content))
        assert uploaded.status_code == 201, uploaded.text
        assert uploaded.json()["amsCharges"] == expected[index]
        entries = db_session.scalars(select(BillingEntry).where(
            BillingEntry.user_id == customer.id, BillingEntry.fee_type == "ams_weight_handling",
        )).all()
        assert {entry.fee_description: (entry.unit_rate, entry.amount) for entry in entries} == {
            fee["feeDescription"]: (Decimal(fee["unitRate"]), Decimal(fee["amount"])) for fee in expected[index]
        }


def test_templates_use_their_own_columns_and_prices(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    login(client, email=admin.email)
    publish(client, ams_config(customer.id))
    template = deepcopy(QLS_CONFIG)
    template["workbook"] = {"sheetMode": "named", "sheetName": "Shipments", "headerRow": 3, "dataStartRow": 4}
    template["amsBilling"] = ams_config(customer.id, match_column="F", weight_column="W")
    template["amsBilling"]["taxHandlingFeeEur"] = "2.00"  # Legacy template amount is ignored.
    template["amsBilling"]["customerRates"][0]["fees"][0]["rateEurPerKg"] = "2.00"
    created = client.post("/api/v1/suppliers", json={"name": "RPL", "config": template})
    assert created.status_code == 201, created.text
    data = upload_data()
    data["supplierId"] = created.json()["id"]
    login(client, email=customer.email)
    result = client.post("/api/v1/waybill-uploads/file", data=data, files=upload_files(workbook(
        [("DE-DHL", 2)], match_index=5, weight_index=22, named=True,
    )))
    assert result.status_code == 201, result.text
    assert result.json()["amsWeightFeeEur"] == "4.00"
    assert result.json()["amsTaxHandlingFeeEur"] == "8.00"


@pytest.mark.parametrize("airport,listed,network,expected_tax", [
    ("AMS", False, "DE-DHL", "8.00"), ("AMS", True, "Unknown", "8.00"),
    ("AMS", True, "de-dhl", "8.00"), ("FRA", True, "DE-DHL", "0.00"),
])
def test_ams_skips_unmatched_channels_customers_and_other_airports(client, db_session, airport, listed, network, expected_tax):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    other = create_test_user(db_session, email="other@example.com")
    login(client, email=admin.email)
    publish(client, ams_config(customer.id if listed else other.id))
    login(client, email=customer.email)
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(airport=airport), files=upload_files(workbook([(network, 2)])))
    assert response.status_code == 201, response.text
    assert response.json()["amsWeightFeeEur"] == "0.00"
    assert response.json()["amsWeightDifferenceFeeEur"] == "0.00"
    assert response.json()["amsTaxHandlingFeeEur"] == expected_tax


@pytest.mark.parametrize("weight", [None, "invalid", -1, "NaN", 0.1234])
def test_invalid_matched_weights_block_estimate_and_upload_without_deductions(client, db_session, weight):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    login(client, email=admin.email)
    publish(client, ams_config(customer.id))
    login(client, email=customer.email)
    content = workbook([("DE-DHL", weight)])
    estimate = client.post("/api/v1/billing/estimate", data={"supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS"}, files={"preAlertFile": ("test.xlsx", content)})
    assert estimate.status_code == 400, estimate.text
    result = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(content))
    assert result.status_code == 400, result.text
    assert db_session.scalars(select(BillingEntry)).all() == []
    assert db_session.scalars(select(WaybillUpload)).all() == []


def test_ams_header_mismatch_blocks_upload_and_balance_includes_all_fees(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="10.00")
    login(client, email=admin.email)
    publish(client, ams_config(customer.id))
    login(client, email=customer.email)
    wrong = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(workbook([("DE-DHL", 2)], header="WRONG")))
    assert wrong.status_code == 400, wrong.text
    insufficient = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(workbook([("DE-DHL", 2)])))
    assert insufficient.status_code == 402, insufficient.text
    assert "22.38" in insufficient.text
    assert db_session.scalars(select(BillingEntry)).all() == []


def test_legacy_global_weight_settings_are_ignored_but_global_tax_still_charges(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    settings = db_session.get(BillingSettings, 1)
    settings.ams_billing = {"taxHandlingFeeEur": "90.00", "customerRates": [{"userId": str(customer.id), "rateEurPerKg": "99.00"}]}
    db_session.commit()
    login(client, email=admin.email)
    archived = client.get("/api/v1/billing/ams-settings")
    assert archived.status_code == 200
    assert archived.json()["config"]["taxHandlingFeeEur"] == "90.00"
    assert client.put("/api/v1/billing/ams-settings", json={"config": None}).status_code == 409
    login(client, email=customer.email)
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(workbook([("DE-DHL", 2)])))
    assert response.status_code == 201, response.text
    assert response.json()["amsWeightFeeEur"] == "0.00"
    assert response.json()["amsTaxHandlingFeeEur"] == "8.00"


def test_template_settings_validate_prices_and_hide_other_customer_rates(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com")
    other = create_test_user(db_session, email="other@example.com")
    login(client, email=admin.email)
    config = ams_config(customer.id)
    config["customerRates"].extend(ams_config(other.id)["customerRates"])
    publish(client, config)
    template = deepcopy(QLS_CONFIG)
    invalid = deepcopy(config)
    invalid["customerRates"][0]["fees"].append(invalid["customerRates"][0]["fees"][0])
    template["amsBilling"] = invalid
    assert client.post(f"/api/v1/suppliers/{QLS_SUPPLIER_ID}/versions", json={"config": template}).status_code == 422
    invalid["customerRates"][0]["fees"] = [{"matchValue": "DE-DHL", "rateEurPerKg": "-1.00"}]
    assert client.post(f"/api/v1/suppliers/{QLS_SUPPLIER_ID}/versions", json={"config": template}).status_code == 422
    login(client, email=customer.email)
    visible = client.get("/api/v1/suppliers").json()["items"][0]["currentVersion"]["config"]["amsBilling"]
    assert [rate["userId"] for rate in visible["customerRates"]] == [str(customer.id)]
    assert client.post(f"/api/v1/suppliers/{QLS_SUPPLIER_ID}/versions", json={"config": template}).status_code == 403


@pytest.mark.parametrize("template_mode", ["none", "empty", "other_customer"])
@pytest.mark.parametrize("admin_upload", [False, True])
def test_global_tax_charges_once_without_weight_eligibility(client, db_session, template_mode, admin_upload):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    other = create_test_user(db_session, email="other@example.com")
    login(client, email=admin.email)
    # The handling fee does not depend on the customs-tax airport list either.
    saved = client.patch("/api/v1/billing/settings", json={
        "unitTaxEur": "3.00", "taxableAirports": [], "amsTaxHandlingFeeEur": "8.00",
    })
    assert saved.status_code == 200, saved.text
    if template_mode == "empty":
        publish(client, {"customerRates": []})
    elif template_mode == "other_customer":
        publish(client, ams_config(other.id))
    if not admin_upload:
        login(client, email=customer.email)
    content = workbook([("DE-DHL", 2), ("Colissimo", 3), ("Other", 4)])
    data = upload_data()
    if admin_upload:
        data["targetUserId"] = str(customer.id)
    estimate = client.post("/api/v1/billing/estimate", data=data, files={"preAlertFile": ("data.xlsx", content)})
    assert estimate.status_code == 200, estimate.text
    assert estimate.json()["amsTaxHandlingFeeEur"] == "8.00"
    assert estimate.json()["amsWeightFeeEur"] == "0.00"
    assert estimate.json()["estimatedTotal"] == "14.00"
    uploaded = client.post("/api/v1/waybill-uploads/file", data=data, files=upload_files(content))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["deductedTotal"] == "14.00"
    fees = db_session.scalars(select(BillingEntry).where(BillingEntry.fee_type == "ams_tax_handling")).all()
    assert len(fees) == 1
    assert fees[0].user_id == customer.id
    assert fees[0].quantity == Decimal("1")
    assert fees[0].amount == Decimal("8.00")


def test_global_tax_changes_only_new_uploads_and_refunds_original_amount(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    login(client, email=customer.email)
    content = workbook([("DE-DHL", 2)])
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(content))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["amsTaxHandlingFeeEur"] == "8.00"
    assert uploaded.json()["deductedTotal"] == "13.00"
    login(client, email=admin.email)
    saved = client.patch("/api/v1/billing/settings", json={
        "unitTaxEur": "3.00", "taxableAirports": ["AMS"], "amsTaxHandlingFeeEur": "9.50",
    })
    assert saved.status_code == 200, saved.text
    login(client, email=customer.email)
    estimate = client.post("/api/v1/billing/estimate", data=upload_data(), files={"preAlertFile": ("data.xlsx", content)})
    assert estimate.json()["amsTaxHandlingFeeEur"] == "9.50"
    original = db_session.scalar(select(BillingEntry).where(BillingEntry.fee_type == "ams_tax_handling"))
    assert original.amount == Decimal("8.00")
    login(client, email=admin.email)
    cancelled = client.post(f"/api/v1/waybill-uploads/{uploaded.json()['uploadId']}/cancel", json={"reason": "test"})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["refundedAmount"] == "13.00"
    assert cancelled.json()["record"]["amsTaxHandlingAmountDeleted"] == "8.00"
    db_session.refresh(customer)
    assert customer.balance == Decimal("100.00")


def test_global_tax_can_be_disabled_without_disabling_weight_fees(client, db_session):
    admin = create_test_user(db_session, email="admin@example.com", role="admin")
    customer = create_test_user(db_session, email="customer@example.com", balance="100.00")
    login(client, email=admin.email)
    publish(client, ams_config(customer.id))
    saved = client.patch("/api/v1/billing/settings", json={
        "unitTaxEur": "3.00", "taxableAirports": ["AMS"], "amsTaxHandlingFeeEur": "0.00",
    })
    assert saved.status_code == 200, saved.text
    login(client, email=customer.email)
    content = workbook([("DE-DHL", 2)])
    estimate = client.post("/api/v1/billing/estimate", data=upload_data(), files={"preAlertFile": ("data.xlsx", content)})
    assert estimate.status_code == 200, estimate.text
    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(content))
    assert uploaded.status_code == 201, uploaded.text
    for body in (estimate.json(), uploaded.json()):
        assert body["amsTaxHandlingFeeEur"] == "0.00"
        assert body["amsWeightFeeEur"] == "1.50"
    assert db_session.scalar(select(BillingEntry).where(BillingEntry.fee_type == "ams_tax_handling")) is None


def test_global_tax_is_included_in_balance_requirement_without_template(client, db_session):
    customer = create_test_user(db_session, email="customer@example.com", balance="12.99")
    login(client, email=customer.email)
    response = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(workbook([("Other", 2)])))
    assert response.status_code == 402, response.text
    assert response.json()["detail"]["required"] == "13.00"
    db_session.refresh(customer)
    assert customer.balance == Decimal("12.99")
    assert db_session.scalars(select(BillingEntry)).all() == []
    assert db_session.scalars(select(WaybillUpload)).all() == []
