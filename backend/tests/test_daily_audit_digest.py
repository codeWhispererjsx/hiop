from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.audit_digest_service import send_daily_audit_digest


def values(enabled=True):
    return {"notifications.daily_audit_email": str(enabled).lower(), "notifications.daily_audit_time": "23:55", "notifications.recipient_email": "ops@example.com", "general.timezone": "UTC"}


def test_daily_audit_digest_does_nothing_when_disabled():
    with patch("app.services.audit_digest_service._all", return_value=values(False)):
        assert send_daily_audit_digest(MagicMock(), datetime(2026, 8, 11, 23, 59, tzinfo=timezone.utc))["status"] == "disabled"


def test_daily_audit_digest_is_not_sent_before_configured_time():
    with patch("app.services.audit_digest_service._all", return_value=values()):
        assert send_daily_audit_digest(MagicMock(), datetime(2026, 8, 11, 22, 0, tzinfo=timezone.utc))["status"] == "not_due"


def test_daily_audit_digest_sends_once_and_records_marker():
    db=MagicMock();db.get.return_value=None;db.query.return_value.filter.return_value.order_by.return_value.all.return_value=[]
    with patch("app.services.audit_digest_service._all", return_value=values()), patch("app.services.audit_digest_service.send_email") as send, patch("app.services.audit_digest_service.create_audit_log"):
        result=send_daily_audit_digest(db,datetime(2026,8,11,23,59,tzinfo=timezone.utc))
    assert result=={"status":"sent","records":0,"date":"2026-08-11"}
    send.assert_called_once();db.commit.assert_called_once()
