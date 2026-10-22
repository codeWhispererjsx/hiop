from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from app.main import app as _app
from app.operations import routes


def test_automation_status_distinguishes_failure_from_last_success(monkeypatch):
    organization_id = uuid4()
    attempted_at = datetime(2026, 5, 4, 12, tzinfo=timezone.utc)
    delivered_at = datetime(2026, 5, 4, 10, tzinfo=timezone.utc)
    failed_email = SimpleNamespace(
        attempted_at=attempted_at,
        delivered_at=None,
        error="SMTP rejected the message",
        status="failed",
    )
    successful_email = SimpleNamespace(delivered_at=delivered_at)
    successful_digest = SimpleNamespace(
        attempted_at=attempted_at,
        delivered_at=delivered_at,
        error=None,
        status="sent",
    )
    query = MagicMock()
    query.filter.return_value = query
    query.order_by.return_value = query
    query.join.return_value = query
    query.first.side_effect = [
        failed_email,
        successful_email,
        successful_digest,
        successful_digest,
        None,
    ]
    db = SimpleNamespace(query=MagicMock(return_value=query))
    scheduler = SimpleNamespace(
        running=True,
        get_job=MagicMock(return_value=object()),
    )
    monkeypatch.setattr(routes, "scheduler", scheduler)
    monkeypatch.setattr(routes.app_settings, "scheduler_enabled", True)
    monkeypatch.setattr(
        routes,
        "user_bundle",
        lambda session, user: {
            "network": {"automatic_scanning": True, "automatic_offline_tickets": True},
            "notifications": {
                "email_notifications": True,
                "daily_audit_email": True,
                "recipient_email": "admin@example.invalid",
            },
            "email": {"configured": True},
        },
    )

    result = routes.automation_status(
        db,
        SimpleNamespace(organization_id=organization_id),
    )

    assert result["email_notifications"]["state"] == "failed"
    assert result["email_notifications"]["last_error"] == "SMTP rejected the message"
    assert result["email_notifications"]["last_success"] == delivered_at.isoformat()
    assert result["daily_audit_email"]["state"] == "running"
    assert result["daily_audit_email"]["last_success"] == delivered_at.isoformat()
    assert result["automatic_offline_incidents"]["state"] == "running"
    assert any(
        call.args[0] == f"automatic_network_scan_{organization_id}"
        for call in scheduler.get_job.call_args_list
    )
