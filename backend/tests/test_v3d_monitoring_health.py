from types import SimpleNamespace

from app.services import monitoring_health_service
from app.services.monitoring_health_service import _health, device_health


def scan(status, latency=None):
    return SimpleNamespace(status=status, response_time=latency)


def test_health_is_unknown_without_observations():
    state, reasons, confidence = _health([])
    assert (state, confidence) == ("Unknown", "Limited")
    assert "Insufficient" in reasons[0]


def test_healthy_health_is_explainable():
    state, reasons, confidence = _health([scan("Online", 4), scan("Online", 5), scan("Online", 4)])
    assert (state, confidence) == ("Healthy", "High")
    assert any("Latest check succeeded" in reason for reason in reasons)


def test_partial_failures_are_degraded_and_complete_failure_unhealthy():
    degraded = _health([scan("Online", 4)] * 9 + [scan("Offline")])
    unhealthy = _health([scan("Offline"), scan("Offline")])
    assert degraded[0] == "Degraded"
    assert unhealthy[0] == "Unhealthy"


def test_high_latency_is_degraded():
    assert _health([scan("Online", 300)] * 3)[0] == "Degraded"


def test_device_health_includes_hostname_for_performance_views(monkeypatch):
    device = SimpleNamespace(id="device-id", hostname="frontdesk-01")
    monkeypatch.setattr(monitoring_health_service, "_scans", lambda *_args: [])

    result = device_health(None, device)

    assert result["hostname"] == "frontdesk-01"
