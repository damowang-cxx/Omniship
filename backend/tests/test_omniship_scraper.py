import pytest

from app.services.omniship_scraper import (
    OmnishipScraper,
    OmnishipScraperError,
    build_summary_hash,
    normalize_cell_text,
    normalize_header,
)


def test_normalize_header_matches_expected_columns():
    assert normalize_header("Status Changed") == "statuschanged"
    assert normalize_header("Out Bound") == "outbound"
    assert normalize_header("Weight(kg)") == "weight(kg)"


def test_normalize_actions_cell_joins_visible_lines():
    assert normalize_cell_text("View\nEdit", action_cell=True) == "View; Edit"
    assert normalize_cell_text("\n  ", action_cell=True) is None


def test_build_column_map_requires_all_expected_headers():
    scraper = OmnishipScraper()

    with pytest.raises(OmnishipScraperError, match="missing expected columns"):
        scraper._build_column_map(["Number", "Status"])


def test_build_column_map_includes_parcels():
    scraper = OmnishipScraper()

    column_map = scraper._build_column_map(
        [
            "Number",
            "Status",
            "Status Changed",
            "Weight(kg)",
            "Received",
            "Parcels",
            "In Warehouse",
            "Released",
            "Out Bound",
            "Actions",
        ]
    )

    assert column_map["parcels_raw"] == 5


def test_summary_hash_ignores_relative_status_changed_text():
    base_row = {
        "number": "176-28780776",
        "status": "noa_received",
        "status_changed_at_raw": "an hour ago",
        "weight_kg_raw": "1035",
        "received_raw": "0",
        "parcels_raw": "78",
        "in_warehouse_raw": "0",
        "released_raw": "0%",
        "outbound_raw": "0",
        "actions_raw": "View",
        "action_href": "https://example.test/air_waybills/176-28780776",
    }
    changed_relative_time = {**base_row, "status_changed_at_raw": "2 hours ago"}

    assert build_summary_hash(base_row) == build_summary_hash(changed_relative_time)


def test_summary_hash_uses_only_stable_business_fields():
    base_row = {
        "number": "176-28780776",
        "status": "noa_received",
        "weight_kg_raw": "1035",
        "received_raw": "0",
        "parcels_raw": "78",
        "in_warehouse_raw": "0",
        "released_raw": "0%",
        "outbound_raw": "0",
        "actions_raw": "View",
        "action_href": "https://example.test/old",
    }
    changed_action_only = {
        **base_row,
        "actions_raw": "Open",
        "action_href": "https://example.test/new",
    }
    changed_status = {**base_row, "status": "released"}

    assert build_summary_hash(base_row) == build_summary_hash(changed_action_only)
    assert build_summary_hash(base_row) != build_summary_hash(changed_status)


def test_extract_destinations_from_detail_text():
    scraper = OmnishipScraper()
    lines = [
        "Destinations",
        "DPD 159 Hamm (DE DPD 159 Hamm)",
        "Germany",
        "Units Received:",
        "0 / 41",
        "Units Outbound: 0 / 0",
        "Total Weight:",
        "373.67 kg",
        "Released: 0%",
        "DE DHL Pickup (DE DHL pick up)",
        "Germany",
        "Units Received: 0 / 37",
        "Units Outbound: 0 / 0",
        "Total Weight: 653.46 kg",
        "Released: 0%",
    ]

    destinations = scraper._extract_destinations(lines)

    assert destinations == [
        {
            "name": "DPD 159 Hamm (DE DPD 159 Hamm)",
            "country": "Germany",
            "units_received_raw": "0 / 41",
            "units_outbound_raw": "0 / 0",
            "total_weight_raw": "373.67 kg",
            "released_raw": "0%",
        },
        {
            "name": "DE DHL Pickup (DE DHL pick up)",
            "country": "Germany",
            "units_received_raw": "0 / 37",
            "units_outbound_raw": "0 / 0",
            "total_weight_raw": "653.46 kg",
            "released_raw": "0%",
        },
    ]
