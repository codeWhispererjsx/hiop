from types import SimpleNamespace

import pytest

from app.api.v1.automation_triggers import ScheduleWrite,_validate_schedule,router
from app.models.automation_triggers import AutomationEventOutbox,AutomationTriggerCorrelationGroup,AutomationTriggerRevision
from app.services.automation_trigger_service import EVENT_CATALOG,preview_subscription,validate_payload,validate_subscription
from app.services.automation_event_outbox_service import publish_internal_event
from app.services.scheduler_service import automation_job_id


def subscription(**overrides):
    values=dict(
        event_type="device_offline",
        filter_definition={"operator":"equals","field":"status","value":"offline"},
        input_mapping={},
        maximum_runs_per_window=5,
        delay_seconds=0,
        correlation_threshold=1,
        maximum_correlation_members=100,
        recovery_event_type=None,
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
        "/automation/dead-letter-events",
        "/automation/correlation-groups",
        "/automation/retention/preview",
        "/automation/reports/summary",
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


def test_persistent_orchestration_models_exist():
    assert AutomationEventOutbox.__tablename__=="automation_event_outbox"
    assert AutomationTriggerCorrelationGroup.__tablename__=="automation_trigger_correlation_groups"
    assert AutomationTriggerRevision.__tablename__=="automation_trigger_revisions"


def test_calendar_schedule_validation_is_bounded_and_timezone_aware():
    base=dict(workflow_id="00000000-0000-0000-0000-000000000001",workflow_version_id="00000000-0000-0000-0000-000000000002",name="Daily review",schedule_type="daily",timezone="UTC",preferred_time="08:30")
    _validate_schedule(ScheduleWrite(**base))
    with pytest.raises(Exception,match="Weekly schedules require"):
        _validate_schedule(ScheduleWrite(**{**base,"schedule_type":"weekly"}))


def test_internal_publisher_creates_safe_transactional_outbox_without_commit():
    class FakeDB:
        def __init__(self):self.added=[];self.flushed=False
        def add(self,row):self.added.append(row)
        def flush(self):self.flushed=True
    db=FakeDB()
    row=publish_internal_event(db,event_type="device_offline",safe_payload={"status":"offline"},status="offline")
    assert row.status=="pending"
    assert db.flushed is True
    assert len(db.added)==1
    with pytest.raises(ValueError,match="prohibited"):
        publish_internal_event(db,event_type="device_offline",safe_payload={"password":"unsafe"})
