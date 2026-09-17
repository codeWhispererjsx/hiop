"""V3D read-only health intelligence over existing monitoring observations."""
from datetime import datetime, timedelta, timezone
from statistics import mean

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.snmp import SNMPInterface, SNMPInterfaceChange, SNMPMetric, SNMPTarget

WINDOWS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
METRICS = {
    "cpu": ("device.cpu_percent", "cpu.percent", "system.cpu_percent"),
    "memory": ("device.memory_percent", "memory.percent", "system.memory_percent"),
    "temperature": ("device.temperature_celsius", "temperature.celsius", "system.temperature_celsius"),
    "uptime": ("device.uptime_seconds", "system.uptime"),
}


def _window(value: str) -> timedelta:
    return WINDOWS.get(value, WINDOWS["24h"])


def _health(scans: list[NetworkScan]):
    if not scans:
        return "Unknown", ["Insufficient monitoring data"], "Limited"
    successes = [row for row in scans if row.status.lower() == "online"]
    failures = [row for row in scans if row.status.lower() == "offline"]
    loss = len(failures) * 100 / len(scans)
    latencies = [row.response_time for row in successes if row.response_time is not None]
    average = mean(latencies) if latencies else None
    latest = scans[-1]
    reasons = []
    if latest.status.lower() == "offline": reasons.append("Last local monitoring check got no response")
    if loss >= 50: reasons.append(f"{loss:.0f}% failed checks in the selected window")
    elif loss >= 5: reasons.append(f"{loss:.0f}% failed checks in the selected window")
    if average is not None and average >= 250: reasons.append(f"Average latency is elevated at {average:.1f} ms")
    if loss >= 50: state = "Unhealthy"
    elif latest.status.lower() == "offline" or loss >= 5 or (average is not None and average >= 250): state = "Degraded"
    else: state, reasons = "Healthy", ["Latest check succeeded", "No meaningful failed-check rate", "Latency is within the health threshold"]
    return state, reasons, "High" if len(scans) >= 3 else "Limited"


def _scans(db: Session, device_id, window: str):
    start = datetime.now(timezone.utc) - _window(window)
    return db.query(NetworkScan).filter(NetworkScan.device_id == device_id, NetworkScan.scanned_at >= start).order_by(NetworkScan.scanned_at).all()


def _telemetry(db: Session, device_id, start):
    targets = db.query(SNMPTarget).filter(SNMPTarget.device_id == device_id).all()
    target_ids = [row.id for row in targets]
    rows = [] if not target_ids else db.query(SNMPMetric).filter(SNMPMetric.target_id.in_(target_ids), SNMPMetric.observed_at >= start).order_by(SNMPMetric.observed_at).all()
    result = {}
    for label, keys in METRICS.items():
        values = [row for row in rows if row.metric_key in keys and row.value_numeric is not None]
        result[label] = None if not values else {"current": float(values[-1].value_numeric), "unit": values[-1].unit or ("seconds" if label == "uptime" else "%" if label in {"cpu", "memory"} else "°C"), "history": [{"timestamp": row.observed_at, "value": float(row.value_numeric)} for row in values]}
    return result, targets, rows


def device_health(db: Session, device: Device, window: str = "24h"):
    scans = _scans(db, device.id, window)
    start = datetime.now(timezone.utc) - _window(window)
    telemetry, targets, metric_rows = _telemetry(db, device.id, start)
    state, reasons, confidence = _health(scans)
    online = [row for row in scans if row.status.lower() == "online"]
    latencies = [row.response_time for row in online if row.response_time is not None]
    known = [row for row in scans if row.status.lower() in {"online", "offline"}]
    failed = [row for row in known if row.status.lower() == "offline"]
    interfaces = []
    for target in targets:
        for interface in db.query(SNMPInterface).filter(SNMPInterface.target_id == target.id, SNMPInterface.monitored.is_(True)).all():
            changes = db.query(SNMPInterfaceChange).filter(SNMPInterfaceChange.interface_id == interface.id, SNMPInterfaceChange.detected_at >= start).order_by(SNMPInterfaceChange.detected_at).all()
            interface_metrics = [row for row in metric_rows if row.interface_index == interface.interface_index]
            interfaces.append({"id": str(interface.id), "name": interface.name or f"ifIndex {interface.interface_index}", "operational_status": interface.operational_status or "unknown", "admin_status": interface.admin_status or "unknown", "speed_bps": interface.speed_bps, "errors": next((float(row.value_numeric) for row in reversed(interface_metrics) if "error" in row.metric_key and row.value_numeric is not None), None), "discards": next((float(row.value_numeric) for row in reversed(interface_metrics) if "discard" in row.metric_key and row.value_numeric is not None), None), "history": [{"timestamp": row.detected_at, "change_type": row.change_type, "fields": row.changed_fields, "before": row.before_values, "after": row.after_values} for row in changes]})
    return {
        "device_id": str(device.id), "window": window, "status": scans[-1].status if scans else "Unknown", "health": state,
        "reasons": reasons, "confidence": confidence, "last_check": scans[-1].scanned_at if scans else None,
        "availability_percent": round(len(online) * 100 / len(known), 2) if known else None,
        "packet_loss_percent": round(len(failed) * 100 / len(known), 2) if len(known) >= 2 else None,
        "latency": None if not latencies else {"current": scans[-1].response_time if scans[-1].status.lower() == "online" else None, "average": round(mean(latencies), 2), "minimum": min(latencies), "maximum": max(latencies)},
        "observations": [{"id": str(row.id), "timestamp": row.scanned_at, "status": row.status, "latency_ms": row.response_time, "source": "Local monitoring", "failure_reason": "No response from this device" if row.status.lower() == "offline" else None} for row in scans],
        "telemetry": telemetry, "interfaces": interfaces,
        "source_status": {"icmp": "available" if scans else "no_data", "snmp": "available" if metric_rows else "unavailable" if targets else "unsupported"},
    }


def summary(db: Session, window: str = "24h", organization_id=None, property_id=None):
    query=db.query(Device)
    if organization_id:
        from app.models.hierarchy import Property
        query=query.join(Property,Device.property_id==Property.id).filter(Property.organization_id==organization_id)
    if property_id:
        query=query.filter(Device.property_id==property_id)
    devices = query.filter(Device.inventory_status != "Retired").all()
    items = [device_health(db, row, window) for row in devices]
    return {"window": window, "monitored": sum(bool(row["observations"]) for row in items), "online": sum(row["status"].lower() == "online" for row in items), "offline": sum(row["status"].lower() == "offline" for row in items), "degraded": sum(row["health"] == "Degraded" for row in items), "unhealthy": sum(row["health"] == "Unhealthy" for row in items), "unknown": sum(row["health"] == "Unknown" for row in items), "devices": items}

