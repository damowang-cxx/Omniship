from copy import deepcopy
from uuid import UUID

from sqlalchemy import select

from app.db.models import SupplierVersion
from app.services.supplier_defaults import QLS_CONFIG
from tests.auth_helpers import create_test_user, login


def test_admin_manages_supplier_versions_and_settings(client, db_session):
    admin = create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    assert login(client, email=admin.email).status_code == 200

    initial = client.get("/api/v1/suppliers")
    assert initial.status_code == 200
    assert [item["name"] for item in initial.json()["items"]] == ["QLS"]

    rpl_config = deepcopy(QLS_CONFIG)
    rpl_config["workbook"] = {
        "sheetMode": "named",
        "sheetName": "Shipments",
        "headerRow": 3,
        "dataStartRow": 4,
    }
    rpl_config["fields"][0]["locatorMode"] = "header"
    rpl_config["fields"][0]["locatorValue"] = "Tracking Reference"
    create_response = client.post(
        "/api/v1/suppliers",
        json={"name": "RPL", "config": rpl_config},
    )
    assert create_response.status_code == 201
    supplier_id = create_response.json()["id"]
    assert create_response.json()["currentVersionNumber"] == 1
    assert client.post(
        "/api/v1/suppliers",
        json={"name": "rpl", "config": rpl_config},
    ).status_code == 400

    updated_config = deepcopy(rpl_config)
    updated_config["fields"][2]["constraints"]["maxValue"] = "30"
    version_response = client.post(
        f"/api/v1/suppliers/{supplier_id}/versions",
        json={"config": updated_config},
    )
    assert version_response.status_code == 200
    assert version_response.json()["currentVersionNumber"] == 2
    versions = db_session.execute(
        select(SupplierVersion)
        .where(SupplierVersion.supplier_id == UUID(supplier_id))
        .order_by(SupplierVersion.version_number)
    ).scalars().all()
    assert versions[0].config["fields"][2]["constraints"]["maxValue"] == "20"
    assert versions[1].config["fields"][2]["constraints"]["maxValue"] == "30"

    settings_response = client.patch(
        "/api/v1/billing/settings",
        json={
            "unitTaxEur": "4.50",
            "taxableAirports": ["ams", "FRA", "AMS"],
            "taxEffectiveDate": "2026-07-01",
        },
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["unitTaxEur"] == "4.50"
    assert settings_response.json()["taxableAirports"] == ["AMS", "FRA"]
    assert settings_response.json()["taxEffectiveDate"] == "2026-07-01"
    assert client.patch(
        "/api/v1/billing/settings",
        json={"unitTaxEur": "3.001", "taxableAirports": ["AMS"]},
    ).status_code == 422

    inactive = client.patch(
        f"/api/v1/suppliers/{supplier_id}",
        json={"status": "inactive"},
    )
    assert inactive.status_code == 200
    assert inactive.json()["status"] == "inactive"


def test_regular_user_only_sees_active_suppliers(client, db_session):
    admin = create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    user = create_test_user(db_session, email="user@example.com", username="User")
    assert login(client, email=admin.email).status_code == 200
    created = client.post(
        "/api/v1/suppliers",
        json={"name": "RPL", "config": QLS_CONFIG},
    ).json()
    client.patch(f"/api/v1/suppliers/{created['id']}", json={"status": "inactive"})

    assert login(client, email=user.email).status_code == 200
    response = client.get("/api/v1/suppliers")
    assert response.status_code == 200
    assert [item["name"] for item in response.json()["items"]] == ["QLS"]
    assert client.post(
        "/api/v1/suppliers", json={"name": "Forbidden", "config": QLS_CONFIG}
    ).status_code == 403


def test_supplier_config_rejects_unsafe_formula_shapes(client, db_session):
    admin = create_test_user(
        db_session,
        email="admin@example.com",
        username="Admin",
        role="admin",
    )
    assert login(client, email=admin.email).status_code == 200
    config = deepcopy(QLS_CONFIG)
    config["fields"][0]["constraints"]["pattern"] = "(a+)+"

    response = client.post(
        "/api/v1/suppliers",
        json={"name": "Unsafe", "config": config},
    )

    assert response.status_code == 422
