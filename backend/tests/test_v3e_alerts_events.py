from types import SimpleNamespace
from app.services.alert_event_service import failed_check_percent,latency_breached,offline_breached

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
