from types import SimpleNamespace

import pytest

from app.api.v1.automation_triggers import router
from app.services.automation_trigger_service import EVENT_CATALOG,preview_subscription,validate_payload,validate_subscription
from app.services.scheduler_service import automation_job_id


def subscription(**overrides):
    values=dict(
        event_type="device_offline",
        filter_definition={"operator":"equals","field":"status","value":"offline"},
        input_mapping={},
        maximum_runs_per_window=5,
        delay_seconds=0,
        trigger_mode="notify_only",
        approval_mode="use_workflow_policy",
        maintenance_behavior="suppress",
        blackout_behavior="suppress",
        blackout_start=None,
        blackout_end=None,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def test_event_catalog_is_fixed_and_contains_supported_modules():
    assert EVENT_CATALOG["device_offline"]["module"]=="devices"
    assert "unknown_user_event" not in EVENT_CATALOG


def test_event_payload_rejects_secrets_and_excessive_nesting():
    with pytest.raises(ValueError,match="prohibited"):
        validate_payload({"token":"hidden"})
    value={"a":{"b":{"c":{"d":{"e":{"f":"too deep"}}}}}}
    with pytest.raises(ValueError,match="nesting"):
        validate_payload(value)


def test_trigger_validation_enforces_allowlisted_fields_and_storm_limits():
    assert validate_subscription(subscription())==[]
    errors=validate_subscription(subscription(filter_definition={"operator":"equals","field":"password","value":"x"},maximum_runs_per_window=101))
    assert any("not allowed" in item for item in errors)
    assert any("safe bounds" in item for item in errors)
    assert any("unsupported path" in item for item in validate_subscription(subscription(input_mapping={"device_id":"metadata.secret"})))
    nested=subscription(filter_definition={"any":[{"field":"password","operator":"equals","value":"x"}]})
    assert any("not allowed" in item for item in validate_subscription(nested))


def test_scheduler_job_ids_are_stable():
    assert automation_job_id("123")=="automation_workflow_123"


def test_orchestration_lifecycle_routes_are_registered_without_public_webhooks():
    paths={route.path for route in router.routes if getattr(route,"path",None)}
    expected={
        "/automation/event-catalogue",
        "/automation/events/{event_id}/reprocess",
        "/automation/trigger-validation",
        "/automation/triggers/{trigger_id}/test",
        "/automation/schedules/{schedule_id}/run-now",
        "/automation/scheduler-status",
    }
    assert expected.issubset(paths)
    assert not any("webhook" in path for path in paths)


def test_trigger_preview_is_side_effect_free_and_maps_allowlisted_inputs():
    row=SimpleNamespace(
        filter_definition='{"field":"status","operator":"equals","value":"offline"}',
        condition_definition=None,
        input_mapping='{"device_id":"source_entity_id"}',
        enabled=True,
        trigger_mode="request_approval",
    )
    event=SimpleNamespace(
        safe_payload={},
        severity="critical",
        status="offline",
        source_entity_id="device-1",
        property_id="property-1",
    )
    result=preview_subscription(row,event)
    assert result["matched"] is True
    assert result["mapped_inputs"]=={"device_id":"device-1"}
