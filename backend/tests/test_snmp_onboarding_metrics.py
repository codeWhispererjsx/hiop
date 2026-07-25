"""Epic 4C operational-layer tests. No SNMP transport is contacted."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.snmp_operational_service import (
    calculate_counter_rate, calculate_utilization, score_inventory_match,
)


@pytest.mark.parametrize(
    "current,previous,elapsed,bits,expected,quality",
    [
        (200, 100, 10, 32, 10, "good"),
        (2**32 - 10, 2**32 - 110, 10, 32, 10, "good"),
        (25, 2**32 - 25, 10, 32, 5, "wrapped"),
        (25, 1000, 10, 32, None, "reset"),
        (100, 100, 10, 64, 0, "good"),
        (100, 50, 0, 64, None, "invalid"),
        (100, 50, -1, 64, None, "invalid"),
        (-1, 50, 10, 64, None, "invalid"),
        (100, -1, 10, 64, None, "invalid"),
        (100, 50, 4000, 64, None, "stale"),
    ],
)
def test_counter_rate_rules(current, previous, elapsed, bits, expected, quality):
    result = calculate_counter_rate(current, previous, elapsed, bits=bits, max_gap_seconds=3600)
    assert result.value == expected
    assert result.quality == quality


def test_counter_rate_reboot_resets_baseline():
    result = calculate_counter_rate(100, 50, 10, rebooted=True)
    assert result.value is None and result.quality == "reset"


@pytest.mark.parametrize(
    "rate,speed,value,quality",
    [
        (500_000_000, 1_000_000_000, 50, "good"),
        (1_100_000_000, 1_000_000_000, 110, "warning"),
        (0, 1_000_000_000, 0, "good"),
        (100, 0, None, "unsupported"),
        (100, None, None, "unsupported"),
        (-100, 1000, None, "invalid"),
    ],
)
def test_utilization_rules(rate, speed, value, quality):
    result = calculate_utilization(rate, speed)
    assert result.value == value
    assert result.quality == quality


def _candidate(**values):
    defaults = dict(id=uuid4(), matched_device_id=None, sys_name="core-sw-1",
                    vendor_guess="Cisco", device_type_guess="switch")
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _target(**values):
    defaults = dict(id=uuid4(), device_id=None, ip_address="10.1.2.3", network_zone_id=uuid4())
    defaults.update(values)
    return SimpleNamespace(**defaults)


def _device(**values):
    defaults = dict(id=uuid4(), hostname="core-sw-1", ip_address="10.1.2.3",
                    brand="Cisco", device_type="switch", network_zone_id=None)
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_explicit_target_link_is_exact():
    device = _device()
    result = score_inventory_match(_candidate(), _target(device_id=device.id), device)
    assert result["score"] == 100
    assert result["level"] == "exact"


def test_explicit_candidate_link_is_exact():
    device = _device()
    result = score_inventory_match(_candidate(matched_device_id=device.id), _target(), device)
    assert result["score"] == 99


def test_sysname_ip_vendor_type_is_strong():
    result = score_inventory_match(_candidate(), _target(), _device())
    assert result["score"] == 90
    assert result["level"] == "strong"
    assert result["recommended_action"] == "enrich"


def test_ip_only_is_weak_and_never_exact():
    result = score_inventory_match(
        _candidate(sys_name="other", vendor_guess=None, device_type_guess=None),
        _target(), _device(hostname="different", brand="Other", device_type="printer"),
    )
    assert result["score"] == 30
    assert result["level"] == "weak"


def test_sysname_only_is_weak():
    result = score_inventory_match(
        _candidate(vendor_guess=None, device_type_guess=None),
        _target(ip_address="10.9.9.9"), _device(ip_address="10.8.8.8"),
    )
    assert result["score"] == 35
    assert result["level"] == "weak"


def test_multiple_identity_conflicts_require_conflict_review():
    result = score_inventory_match(
        _candidate(), _target(ip_address="10.9.9.9"),
        _device(hostname="other", ip_address="10.8.8.8"),
    )
    assert {"hostname", "ip_address"}.issubset(result["conflicting_fields"])


def test_operational_routes_are_registered():
    client = TestClient(app)
    paths = client.app.openapi()["paths"]
    expected = {
        "/api/v1/snmp/targets/{target_id}/collect",
        "/api/v1/snmp/candidates/{candidate_id}/match",
        "/api/v1/snmp/candidates/{candidate_id}/onboarding-plan",
        "/api/v1/snmp/candidates/{candidate_id}/approve",
        "/api/v1/snmp/candidates/{candidate_id}/link",
        "/api/v1/snmp/candidates/{candidate_id}/enrich",
        "/api/v1/snmp/targets/{target_id}/interfaces",
        "/api/v1/snmp/interfaces/{interface_id}/changes",
        "/api/v1/snmp/targets/{target_id}/metric-summary",
        "/api/v1/snmp/retention/preview",
        "/api/v1/snmp/state-changes",
    }
    assert expected.issubset(paths)


def test_collection_schema_rejects_arbitrary_oid_inputs():
    schema = app.openapi()["components"]["schemas"]["SNMPCollectionRequest"]
    assert set(schema["properties"]) == {"groups"}
