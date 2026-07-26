"""Epic 4E unit tests. No network operation is performed."""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.snmp import SNMPAlertRuleWrite, SNMPPollingConfigurationWrite
from app.services.scheduler_service import _snmp_schedulable, snmp_job_id
from app.services.snmp_alert_service import SNMPAlertService


def test_deterministic_job_ids_are_group_scoped():
    target_id = str(uuid4())
    assert snmp_job_id(target_id, "availability") == f"snmp_poll_{target_id}_availability"
    assert snmp_job_id(target_id, "system") != snmp_job_id(target_id, "availability")


@pytest.mark.parametrize("disabled", ["target", "polling", "credential"])
def test_disabled_dependency_is_not_schedulable(monkeypatch, disabled):
    monkeypatch.setattr("app.services.scheduler_service.settings.snmp_enabled", True)
    target = SimpleNamespace(enabled=disabled != "target", polling_enabled=disabled != "polling")
    config = SimpleNamespace(enabled=True)
    credential = SimpleNamespace(enabled=disabled != "credential")
    assert not _snmp_schedulable(target, config, credential)


def test_all_dependencies_are_required_for_schedule(monkeypatch):
    monkeypatch.setattr("app.services.scheduler_service.settings.snmp_enabled", True)
    assert _snmp_schedulable(
        SimpleNamespace(enabled=True, polling_enabled=True),
        SimpleNamespace(enabled=True),
        SimpleNamespace(enabled=True),
    )


def test_poll_schedule_bounds_and_safe_defaults():
    config = SNMPPollingConfigurationWrite()
    assert config.availability_interval_seconds == 300
    assert config.interface_inventory_interval_seconds == 3600
    assert config.jitter_seconds == 30
    with pytest.raises(ValidationError):
        SNMPPollingConfigurationWrite(availability_interval_seconds=10)


def test_threshold_rule_requires_threshold():
    with pytest.raises(ValidationError):
        SNMPAlertRuleWrite(
            name="CPU threshold", rule_type="metric_threshold",
            metric_key="device.cpu_percent", comparison_operator="greater_than",
        )


def test_interface_rule_requires_target():
    with pytest.raises(ValidationError):
        SNMPAlertRuleWrite(
            name="Interface down", rule_type="interface_down", interface_id=uuid4(),
            comparison_operator="state_changed",
        )


def test_rule_evaluation_uses_consecutive_breaches():
    service = SNMPAlertService(SimpleNamespace())
    rule = SimpleNamespace(
        comparison_operator="greater_than_or_equal", warning_threshold=80,
        critical_threshold=None, minimum_samples=2, consecutive_breaches=2,
    )
    samples = [
        SimpleNamespace(value_numeric=95, quality="good"),
        SimpleNamespace(value_numeric=85, quality="good"),
        SimpleNamespace(value_numeric=20, quality="good"),
    ]
    assert service._breached(rule, samples)
    samples[1].value_numeric = 70
    assert not service._breached(rule, samples)


def test_missing_rule_is_safe_without_samples():
    service = SNMPAlertService(SimpleNamespace())
    rule = SimpleNamespace(comparison_operator="missing")
    assert service._breached(rule, [])
