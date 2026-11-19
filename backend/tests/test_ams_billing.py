from copy import deepcopy
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.db.models import BillingEntry, BillingSettings, WaybillUpload
from app.services.supplier_defaults import QLS_CONFIG, QLS_SUPPLIER_ID
from tests.auth_helpers import create_test_user, login
from tests.test_supplier_billing_flow import upload_data, upload_files


def ams_config(customer_id, *, match_column="E", weight_column="V", tax="4.25"):
    return {
        "taxHandlingFeeEur": tax, "matchColumn": match_column,
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
        "supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS", "grossWeightKg": "999"
    }, files={"preAlertFile": ("data.xlsx", content)})
    assert estimate.status_code == 200, estimate.text
    charges = estimate.json()["amsCharges"]
    assert charges == [
        {"feeDescription": "DE-DHL", "quantity": "4.000", "unitRate": "0.75", "amount": "3.00"},
        {"feeDescription": "Colissimo", "quantity": "3.500", "unitRate": "1.20", "amount": "4.20"},
    ]
    assert estimate.json()["amsWeightFeeEur"] == "7.20"
    assert estimate.json()["amsTaxHandlingFeeEur"] == "4.25"
    assert estimate.json()["estimatedTotal"] == "31.45"

    uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(), files=upload_files(content))
    assert uploaded.status_code == 201, uploaded.text
    assert uploaded.json()["amsCharges"] == charges
    assert uploaded.json()["deductedTotal"] == "31.45"
    assert uploaded.json()["balanceAfter"] == "68.55"
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
    assert cancelled.json()["refundedAmount"] == "31.45"
    assert cancelled.json()["record"]["amsWeightFeeAmountDeleted"] == "7.20"
    db_session.refresh(customer)
    assert customer.balance == Decimal("100.00")


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
            "supplierId": str(QLS_SUPPLIER_ID), "airportOfArrival": "AMS",
        }, files={"preAlertFile": ("data.xlsx", content)})
        assert estimate.status_code == 200, estimate.text
        assert estimate.json()["amsCharges"] == expected[index]
        uploaded = client.post("/api/v1/waybill-uploads/file", data=upload_data(number=f"784-8406327{index}"), files=upload_files(content))
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
    template["amsBilling"] = ams_config(customer.id, match_column="F", weight_column="W", tax="2.00")
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
    assert result.json()["amsTaxHandlingFeeEur"] == "2.00"


@pytest.mark.parametrize("airport,listed,network,expected_tax", [
    ("AMS", False, "DE-DHL", "4.25"), ("AMS", True, "Unknown", "4.25"),
    ("AMS", True, "de-dhl", "4.25"), ("FRA", True, "DE-DHL", "0.00"),
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
    assert "10.75" in insufficient.text
    assert db_session.scalars(select(BillingEntry)).all() == []


def test_legacy_global_ams_settings_do_not_charge_unconfigured_templates(client, db_session):
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
    assert response.json()["amsTaxHandlingFeeEur"] == "0.00"


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
