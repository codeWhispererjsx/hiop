from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1.system_maintenance import RuleWrite, create_rule, maintenance_log, run_maintenance_rules, system_health, update_rule


def rule_payload(**overrides):
    payload = {
        "name": "Nightly update",
        "criteria": {"uptime_hours": 48},
        "schedule": {"frequency": "daily", "time": "21:30", "timezone": "Africa/Lagos"},
        "action": "TRIGGER_WINDOWS_UPDATE",
    }
    return payload | overrides


def test_maintenance_rule_accepts_allowlisted_conditions_and_schedule():
    rule = RuleWrite(**rule_payload())

    assert rule.criteria == {"uptime_hours": 48}
    assert rule.schedule["timezone"] == "Africa/Lagos"
    assert rule.enabled is False


@pytest.mark.parametrize(
    "overrides",
    [
        {"action": "EXECUTE_COMMAND"},
        {"name": "  "},
        {"criteria": {"uptime_hours": True}},
        {"criteria": {"department": "   "}},
        {"schedule": {"frequency": "daily", "time": 2130, "timezone": "Africa/Lagos"}},
        {"schedule": {"frequency": "weekly", "time": "21:30", "timezone": "Africa/Lagos", "weekday": True}},
        {"schedule": {"frequency": "daily", "time": "21:30", "timezone": "Africa/Lagos", "weekday": 1}},
    ],
)
def test_maintenance_rule_rejects_invalid_or_unbounded_values(overrides):
    with pytest.raises(ValidationError):
        RuleWrite(**rule_payload(**overrides))

def test_scheduled_endpoint_actions_cannot_be_created_or_updated():
    body=RuleWrite(**rule_payload())
    with pytest.raises(HTTPException) as create_error:
        create_rule(body,MagicMock(),SimpleNamespace(username="admin",id="user-id"),"organization-id")
    assert create_error.value.status_code==409
    with pytest.raises(HTTPException) as update_error:
        update_rule(uuid4(),body,MagicMock(),SimpleNamespace(username="admin",id="user-id"),"organization-id")
    assert update_error.value.status_code==409

def test_scheduler_disables_legacy_rules_without_queuing_actions(monkeypatch):
    rule=SimpleNamespace(id=uuid4(),organization_id=uuid4(),property_id=uuid4(),enabled=True,updated_at=None)
    query=MagicMock()
    query.filter_by.return_value.all.return_value=[rule]
    db=MagicMock()
    db.query.return_value=query
    audit=MagicMock()
    monkeypatch.setattr("app.db.database.SessionLocal",lambda:db)
    monkeypatch.setattr("app.api.v1.system_maintenance.create_audit_log",audit)

    run_maintenance_rules()

    assert rule.enabled is False
    assert rule.updated_at is not None
    db.add.assert_not_called()
    db.commit.assert_called_once()
    assert audit.call_args.args[2]=="MAINTENANCE_RULE_DISABLED"


def test_custom_maintenance_log_requires_ordered_dates():
    with pytest.raises(HTTPException) as error:
        maintenance_log(
            "custom",
            MagicMock(),
            SimpleNamespace(),
            "organization-id",
            date(2026, 10, 27),
            date(2026, 10, 26),
        )

    assert error.value.status_code == 422


def test_system_health_marks_unmanaged_device_without_agent(monkeypatch):
    property_id = UUID("22222222-2222-2222-2222-222222222222")
    device = SimpleNamespace(
        id=uuid4(),
        property_id=property_id,
        hostname="frontdesk-01",
        department="Front Office",
        location="Reception",
        ip_address="10.0.0.10",
        inventory_status="Active",
    )
    device_query = MagicMock()
    device_query.join.return_value.outerjoin.return_value.filter.return_value.all.return_value = [(device, None)]
    agent_query = MagicMock()
    agent_query.filter.return_value.order_by.return_value.all.return_value = []
    job_query = MagicMock()
    job_query.filter.return_value.all.return_value = []
    db = MagicMock()
    db.query.side_effect = [device_query, agent_query, job_query]
    monkeypatch.setattr("app.api.v1.system_maintenance.allowed_property_ids", lambda *_: [property_id])

    report = system_health(db, SimpleNamespace(), "organization-id")

    assert report["summary"]["total_devices"] == 1
    assert report["summary"]["hygiene_score"] == 0
    assert report["devices"][0]["status"] == "No agent"
