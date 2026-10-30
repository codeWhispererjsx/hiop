from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.api.v1.local_agents import EnrollRequest, PowerEventWrite, agent_view, enroll, heartbeat, report_power_event


def agent(**values):
    base = {
        "id": "agent-row",
        "agent_id": "HIOP-AGENT-TEST",
        "organization_id": "11111111-1111-1111-1111-111111111111",
        "property_id": "22222222-2222-2222-2222-222222222222",
        "version": "1.3.0",
        "hostname": "workstation",
        "last_heartbeat": None,
        "uptime_seconds": None,
        "pending_queue": 0,
        "queue_capacity": 10000,
        "registered_at": datetime.now(timezone.utc),
        "revoked_at": None,
        "retired_at": None,
    }
    return SimpleNamespace(**(base | values))


def test_heartbeat_stores_power_health_and_returns_local_lock_policy():
    db = MagicMock()
    db.query.return_value.filter_by.return_value.order_by.return_value.first.return_value = None
    target = agent()
    body = SimpleNamespace(
        version="1.3.0",
        hostname="workstation",
        uptime_seconds=9 * 24 * 60 * 60,
        pending_queue=0,
        queue_capacity=10000,
        fast_startup_enabled=True,
        lid_close_action="AC Sleep / DC Hibernate",
        battery_health_percent=78.5,
        pending_windows_updates=3,
        last_shutdown_at=datetime.now(timezone.utc),
        cpu_percent=None,
        memory_total_bytes=None,
        memory_free_bytes=None,
        disk_free_bytes=None,
        ip_address=None,
        operating_system=None,
        logged_user=None,
        last_update=None,
        model_fields_set={
            "fast_startup_enabled",
            "lid_close_action",
            "battery_health_percent",
            "pending_windows_updates",
            "last_shutdown_at",
        },
    )

    result = heartbeat(body, db, target)

    assert target.fast_startup_enabled is True
    assert target.lid_close_action == "AC Sleep / DC Hibernate"
    assert target.battery_health_percent == 78.5
    assert target.pending_windows_updates == 3
    assert target.last_shutdown_at == body.last_shutdown_at
    assert result["smart_lock_timeout_seconds"] == 300


def test_agent_view_includes_nullable_health_telemetry():
    target = agent(
        fast_startup_enabled=False,
        lid_close_action=None,
        battery_health_percent=None,
        pending_windows_updates=0,
        last_shutdown_at=None,
    )

    result = agent_view(target)

    assert result["fast_startup_enabled"] is False
    assert result["lid_close_action"] is None
    assert result["battery_health_percent"] is None
    assert result["pending_windows_updates"] == 0
    assert result["last_shutdown_at"] is None


def test_power_events_are_scoped_and_audited(monkeypatch):
    audit = MagicMock()
    monkeypatch.setattr("app.api.v1.local_agents.create_audit_log", audit)
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = None
    target = agent()
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.20"))
    body = PowerEventWrite(
        event_id="55555555-5555-5555-5555-555555555555",
        event_type="END_OF_DAY_STAY_ON",
        occurred_at=datetime.now(timezone.utc),
        reason="Overnight maintenance",
    )

    result = report_power_event(body, request, db, target)

    stored = next(call.args[0] for call in db.add.call_args_list if hasattr(call.args[0], "event_type"))
    assert stored.agent_id == target.id
    assert stored.organization_id == target.organization_id
    assert stored.property_id == target.property_id
    assert stored.reason == "Overnight maintenance"
    assert result == {"status": "recorded"}
    assert audit.call_args.args[2] == "LOCAL_AGENT_END_OF_DAY_STAY_ON"
    assert audit.call_args.kwargs["source_ip"] == "192.0.2.20"


def test_agent_enrollment_is_audited_in_the_enrollment_scope(monkeypatch):
    audit = MagicMock()
    monkeypatch.setattr("app.api.v1.local_agents.create_audit_log", audit)
    monkeypatch.setattr("app.api.v1.local_agents.enrollment_limiter.check", lambda *_args: None)
    enrollment = SimpleNamespace(
        id="enrollment-1",
        organization_id="11111111-1111-1111-1111-111111111111",
        property_id="22222222-2222-2222-2222-222222222222",
        name="Front desk PC",
        created_by="user-1",
        used_at=None,
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = enrollment
    db.query.return_value.filter.return_value.limit.return_value.all.return_value = []
    request = SimpleNamespace(client=SimpleNamespace(host="192.0.2.30"))

    result = enroll(EnrollRequest(enrollment_token="t" * 40, hostname="FRONTDESK-01", version="1.3.0"), request, db)

    assert enrollment.used_at is not None
    assert audit.call_args.args[1] == result["agent_id"]
    assert audit.call_args.args[2] == "AGENT_ENROLLED"
    assert "FRONTDESK-01" in audit.call_args.args[5]
    assert audit.call_args.kwargs["organization_id"] == enrollment.organization_id
    assert audit.call_args.kwargs["property_id"] == enrollment.property_id
    db.commit.assert_called_once()


def test_power_event_retry_with_same_id_is_idempotent():
    existing = SimpleNamespace(event_id="55555555-5555-5555-5555-555555555555")
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = existing

    response = report_power_event(
        PowerEventWrite(
            event_id=existing.event_id,
            event_type="END_OF_DAY_NUDGE",
            occurred_at=datetime.now(timezone.utc),
        ),
        SimpleNamespace(client=SimpleNamespace(host="192.0.2.20")),
        db,
        agent(),
    )

    assert response == {"status": "duplicate"}
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_smart_lock_request_event_is_accepted():
    event = PowerEventWrite(
        event_id="55555555-5555-5555-5555-555555555555",
        event_type="SMART_LOCK_REQUESTED",
        occurred_at=datetime.now(timezone.utc),
    )

    assert event.event_type == "SMART_LOCK_REQUESTED"


@pytest.mark.parametrize(
    "values",
    [
        {"event_type": "END_OF_DAY_STAY_ON", "reason": None, "occurred_at": datetime.now(timezone.utc)},
        {"event_type": "SMART_LOCK_APPLIED", "reason": None, "occurred_at": datetime.now()},
        {
            "event_type": "END_OF_DAY_NUDGE",
            "reason": None,
            "occurred_at": datetime.now(timezone.utc).replace(year=datetime.now(timezone.utc).year + 1),
        },
    ],
)
def test_power_events_reject_missing_reason_naive_time_and_future_time(values):
    with pytest.raises(ValidationError):
        PowerEventWrite(event_id="55555555-5555-5555-5555-555555555555", **values)
