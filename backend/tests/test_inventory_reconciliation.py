from types import SimpleNamespace
from uuid import uuid4

from app.services.inventory_reconciliation_service import (
    find_imported_asset_candidates,
    index_imported_assets,
)

PROPERTY_ID = uuid4()


def _asset(
    *,
    name="heloshadtfo1115",
    serial_number=None,
    source="inventory_import",
    device_id=None,
    status="active",
):
    return SimpleNamespace(
        id=uuid4(),
        property_id=PROPERTY_ID,
        asset_number="HIOP-000001",
        name=name,
        serial_number=serial_number,
        source=source,
        device_id=device_id,
        status=status,
        department_name="Front Office",
        location_name="Room 101",
    )


def _result(**overrides):
    values = {
        "property_id": PROPERTY_ID,
        "primary_hostname": "HELOSHADTFO1115",
        "fqdn": None,
        "ad_computer_name": None,
        "serial_number": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_imported_asset_matches_exact_hostname_case_insensitively():
    asset = _asset()

    matches = find_imported_asset_candidates(_result(), index_imported_assets([asset]))

    assert matches == [
        {
            "asset_id": str(asset.id),
            "asset_number": "HIOP-000001",
            "name": "heloshadtfo1115",
            "department": "Front Office",
            "location": "Room 101",
            "matched_fields": ["hostname"],
        }
    ]


def test_imported_asset_matches_exact_serial_when_hostname_changed():
    asset = _asset(name="old-hostname", serial_number="SN-123")

    matches = find_imported_asset_candidates(
        _result(primary_hostname="new-hostname", serial_number=" sn-123 "),
        index_imported_assets([asset]),
    )

    assert len(matches) == 1
    assert matches[0]["matched_fields"] == ["serial_number"]


def test_imported_asset_candidates_include_ambiguous_matches_for_review():
    assets = [_asset(name="same-host"), _asset(name="SAME-HOST")]

    matches = find_imported_asset_candidates(
        _result(primary_hostname="same-host"),
        index_imported_assets(assets),
    )

    assert len(matches) == 2
    assert all(match["matched_fields"] == ["hostname"] for match in matches)


def test_non_imported_linked_and_retired_assets_are_not_suggested():
    assets = [
        _asset(source="manual"),
        _asset(device_id=uuid4()),
        _asset(status="retired"),
    ]

    assert find_imported_asset_candidates(_result(), index_imported_assets(assets)) == []


def test_unusable_serial_does_not_create_a_candidate():
    asset = _asset(name="different-host", serial_number="Unknown")

    assert find_imported_asset_candidates(
        _result(primary_hostname=None, serial_number="unknown"),
        index_imported_assets([asset]),
    ) == []
