from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.main import app as _app
from app.services import scheduler_service


def test_scheduled_network_scan_uses_organization_settings_and_scope(monkeypatch):
    organization_id = uuid4()
    db = SimpleNamespace(info={}, close=Mock())
    scanned = Mock(return_value={"total_devices": 0, "online": 0, "offline": 0})
    monkeypatch.setattr(scheduler_service, "SessionLocal", lambda: db)
    monkeypatch.setattr(scheduler_service, "scan_all_devices", scanned)
    monkeypatch.setattr(
        "app.services.settings_service.read_network",
        lambda session: {"automatic_scanning": True},
    )

    scheduler_service.scheduled_network_scan(str(organization_id))

    assert db.info["organization_id"] == organization_id
    scanned.assert_called_once_with(db, organization_id=organization_id)
    db.close.assert_called_once()


def test_scheduled_network_scan_skips_disabled_organization(monkeypatch):
    db = SimpleNamespace(info={}, close=Mock())
    scanned = Mock()
    monkeypatch.setattr(scheduler_service, "SessionLocal", lambda: db)
    monkeypatch.setattr(scheduler_service, "scan_all_devices", scanned)
    monkeypatch.setattr(
        "app.services.settings_service.read_network",
        lambda session: {"automatic_scanning": False},
    )

    scheduler_service.scheduled_network_scan(str(uuid4()))

    scanned.assert_not_called()
    db.close.assert_called_once()


def test_organization_scan_job_has_a_tenant_specific_scheduler_id(monkeypatch):
    organization_id = uuid4()
    jobs = Mock()
    fake_scheduler = SimpleNamespace(running=True, get_job=Mock(return_value=None), add_job=jobs)
    monkeypatch.setattr(scheduler_service, "scheduler", fake_scheduler)
    monkeypatch.setattr(scheduler_service.settings, "scheduler_enabled", True)

    scheduler_service.configure_scheduler(True, 15, organization_id)

    assert fake_scheduler.add_job.call_args.kwargs["id"] == f"automatic_network_scan_{organization_id}"
    assert fake_scheduler.add_job.call_args.kwargs["args"] == [str(organization_id)]
