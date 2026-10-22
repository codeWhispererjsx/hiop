import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from app.main import app as _app
from app.models.device import Device
from app.models.discovery_intelligence import DiscoveryJob
from app.models.hierarchy import Property
from app.models.network_scan import NetworkScan
from app.models.system_health import JobExecution
from app.operations import routes


def _query(rows=None, count=None):
    query = MagicMock()
    query.join.return_value = query
    query.filter.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.first.return_value = rows
    query.all.return_value = rows or []
    query.count.return_value = count or 0
    return query


def test_local_operations_dashboard_returns_scoped_real_status(monkeypatch):
    organization_id = uuid4()
    now = datetime(2026, 5, 4, 12, tzinfo=timezone.utc)
    latest_scan = SimpleNamespace(scanned_at=now, status="Online")
    latest_discovery = SimpleNamespace(
        completed_at=now,
        started_at=now,
        created_at=now,
        status="completed",
        hosts_completed=8,
        hosts_total=10,
    )
    queries = {
        Device: _query(count=7),
        NetworkScan: _query(latest_scan),
        DiscoveryJob: _query(latest_discovery),
        JobExecution: _query([]),
    }
    db = SimpleNamespace(
        info={},
        execute=Mock(return_value=SimpleNamespace(scalar_one=Mock(return_value=1))),
        query=Mock(side_effect=lambda model: queries[model]),
        rollback=Mock(),
    )
    monkeypatch.setattr(routes, "make_url", lambda value: SimpleNamespace(get_backend_name=lambda: "postgresql", database=None))
    monkeypatch.setattr(
        routes.socket,
        "getaddrinfo",
        lambda *args: [(None, None, None, None, ("192.168.20.10", 0))],
    )
    monkeypatch.setattr(routes, "scheduler", SimpleNamespace(running=False, get_jobs=lambda: []))
    user = SimpleNamespace(organization_id=organization_id)

    result = routes._local_operations_payload(db, user, organization_id)

    assert result["service"]["status"] == "running"
    assert result["database"]["status"] == "available"
    assert result["network"]["ipv4_addresses"] == ["192.168.20.10"]
    assert result["discovery"]["hosts_completed"] == 8
    assert result["monitored_devices"]["total"] == 7
    assert result["backup"]["status"] == "managed_by_platform"
    assert result["storage"]["available_bytes"] is None
    assert result["recent_errors"] == []
    assert queries[Device].join.call_count == 1
    assert queries[Device].join.call_args.args[0] is Property


def test_local_operations_reports_database_failure_without_success_fallback():
    db = SimpleNamespace(
        execute=Mock(side_effect=SQLAlchemyError("connection unavailable")),
        rollback=Mock(),
        query=Mock(),
    )
    result = routes._local_operations_payload(db, SimpleNamespace(organization_id=uuid4()), uuid4())
    assert result["service"]["status"] == "running"
    assert result["database"]["status"] == "unavailable"
    assert result["monitored_devices"]["total"] is None
    db.rollback.assert_called_once()
    db.query.assert_not_called()


def test_support_report_excludes_network_addresses_and_audits_download(monkeypatch):
    organization_id = uuid4()
    payload = {
        "service": {"status": "running"},
        "database": {"status": "available"},
        "network": {"ipv4_addresses": ["192.168.20.10"]},
        "discovery": {"result": "completed"},
        "monitored_devices": {"total": 4},
        "backup": {"status": "success"},
        "storage": {"available_bytes": 1000},
        "recent_errors": [],
    }
    db = SimpleNamespace(commit=Mock())
    audit = Mock()
    monkeypatch.setattr(routes, "_local_operations_payload", lambda session, user, org: payload)
    monkeypatch.setattr(routes, "create_audit_log", audit)
    user = SimpleNamespace(username="administrator", organization_id=organization_id)

    response = routes.download_local_support_report(db, user, organization_id)
    report = json.loads(response.body)

    assert response.headers["cache-control"] == "no-store"
    assert "192.168.20.10" not in response.body.decode()
    assert "credentials, tokens, private keys" in report["privacy_notice"]
    audit.assert_called_once()
    db.commit.assert_called_once()
