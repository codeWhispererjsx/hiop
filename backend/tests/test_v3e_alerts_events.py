from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.alerts_events import Resolution, acknowledge, resolve, rules
from app.models.alert import AlertHistory
from app.services.alert_event_service import failed_check_percent,latency_breached,offline_breached
from app.services.network_service import offline_threshold_crossed

def scan(status="Online",latency=None):return SimpleNamespace(status=status,response_time=latency)
def test_single_failure_is_debounced():assert not offline_breached([scan("Offline")],3)
def test_consecutive_failures_trigger_offline_rule():assert offline_breached([scan("Offline")]*3,3)
def test_recovery_breaks_offline_condition():assert not offline_breached([scan("Online"),scan("Offline"),scan("Offline")],3)
def test_latency_requires_sustained_threshold():
    assert latency_breached([scan(latency=120)]*3,3,100)
    assert not latency_breached([scan(latency=120),scan(latency=80),scan(latency=120)],3,100)
def test_packet_loss_uses_recorded_checks_only():
    assert failed_check_percent([scan("Online")]) is None
    assert failed_check_percent([scan("Offline"),scan("Online"),scan("Online"),scan("Online")])==25
def test_automatic_offline_incident_triggers_only_when_threshold_is_crossed():
    assert not offline_threshold_crossed("Offline",[],3)
    assert not offline_threshold_crossed("Offline",[scan("Offline")],3)
    assert offline_threshold_crossed("Offline",[scan("Offline"),scan("Offline")],3)
    assert not offline_threshold_crossed("Offline",[scan("Online"),scan("Offline")],3)

def test_acknowledgement_records_scoped_audit_and_history():
    alert = SimpleNamespace(
        id=uuid4(), device_id=uuid4(), title="Device offline",
        lifecycle_status="open", acknowledged=False, acknowledged_by=None,
        acknowledged_at=None, last_updated_at=None,
    )
    organization_id, property_id = uuid4(), uuid4()
    actor = SimpleNamespace(id="admin-1", username="admin")
    db = MagicMock()
    db.get.return_value = SimpleNamespace(property_id=property_id)
    with patch("app.api.v1.alerts_events.scoped_alert", return_value=alert), \
         patch("app.api.v1.alerts_events.view", return_value={"id": str(alert.id)}) as alert_view, \
         patch("app.api.v1.alerts_events.create_audit_log") as audit:
        result = acknowledge(alert.id, db, actor, organization_id, property_id)

    assert alert.lifecycle_status == "acknowledged"
    assert alert.acknowledged_by == actor.id
    history = next(item for item in db.add.call_args_list[0].args if isinstance(item, AlertHistory))
    assert history.current_status == "acknowledged"
    audit.assert_called_once_with(
        db, actor.username, "ALERT_ACKNOWLEDGED", "Alert", str(alert.id),
        alert.title, organization_id=organization_id, property_id=property_id,
    )
    db.commit.assert_called_once()
    alert_view.assert_called_once_with(db, alert)
    assert result == {"id": str(alert.id)}

def test_repeated_acknowledgement_is_idempotent():
    alert = SimpleNamespace(id=uuid4(), lifecycle_status="acknowledged")
    db = MagicMock()
    with patch("app.api.v1.alerts_events.scoped_alert", return_value=alert), \
         patch("app.api.v1.alerts_events.view", return_value={"id": str(alert.id)}) as alert_view, \
         patch("app.api.v1.alerts_events.create_audit_log") as audit:
        result = acknowledge(
            alert.id, db, SimpleNamespace(id="admin", username="admin"), uuid4(), None
        )

    assert result == {"id": str(alert.id)}
    alert_view.assert_called_once_with(db, alert)
    audit.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()

def test_resolving_alert_requires_reason_and_records_scoped_history():
    alert = SimpleNamespace(
        id=uuid4(), device_id=uuid4(), title="High latency",
        lifecycle_status="acknowledged", resolved_by=None, resolved_at=None,
        resolution_reason=None, manually_resolved=False, last_updated_at=None,
    )
    organization_id, property_id = uuid4(), uuid4()
    actor = SimpleNamespace(id="tech-1", username="technician")
    db = MagicMock()
    db.get.return_value = SimpleNamespace(property_id=property_id)
    with patch("app.api.v1.alerts_events.scoped_alert", return_value=alert), \
         patch("app.api.v1.alerts_events.view", return_value={"id": str(alert.id)}), \
         patch("app.api.v1.alerts_events.create_audit_log") as audit:
        resolve(alert.id, Resolution(reason="Network repaired"), db, actor, organization_id, property_id)

    assert alert.lifecycle_status == "resolved"
    assert alert.resolved_by == actor.id
    assert alert.resolution_reason == "Network repaired"
    history = next(item for item in db.add.call_args_list[0].args if isinstance(item, AlertHistory))
    assert history.previous_status == "acknowledged"
    assert history.current_status == "resolved"
    audit.assert_called_once_with(
        db, actor.username, "ALERT_MANUALLY_RESOLVED", "Alert", str(alert.id),
        "Network repaired", organization_id=organization_id, property_id=property_id,
    )
    db.commit.assert_called_once()

def test_resolved_alert_cannot_be_resolved_twice():
    alert = SimpleNamespace(id=uuid4(), lifecycle_status="resolved")
    with patch("app.api.v1.alerts_events.scoped_alert", return_value=alert):
        with pytest.raises(HTTPException) as error:
            resolve(alert.id, Resolution(reason="Again"), MagicMock(), SimpleNamespace(username="admin"), uuid4(), None)
    assert error.value.status_code == 409

def test_rules_response_matches_frontend_items_contract():
    rule = SimpleNamespace(rule_type="device_offline", organization_id=None, property_id=None)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [rule]

    result = rules(db, SimpleNamespace(), uuid4(), None)

    assert result == {"items": [rule]}
