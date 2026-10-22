"""V3D read-only health intelligence over existing monitoring observations."""
from datetime import datetime, timedelta, timezone
from statistics import mean

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.network_scan import NetworkScan

WINDOWS = {"1h": timedelta(hours=1), "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
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


def device_health(db: Session, device: Device, window: str = "24h"):
    scans = _scans(db, device.id, window)
    state, reasons, confidence = _health(scans)
    online = [row for row in scans if row.status.lower() == "online"]
    latencies = [row.response_time for row in online if row.response_time is not None]
    known = [row for row in scans if row.status.lower() in {"online", "offline"}]
    failed = [row for row in known if row.status.lower() == "offline"]
    return {
        "device_id": str(device.id), "window": window, "status": scans[-1].status if scans else "Unknown", "health": state,
        "reasons": reasons, "confidence": confidence, "last_check": scans[-1].scanned_at if scans else None,
        "availability_percent": round(len(online) * 100 / len(known), 2) if known else None,
        "packet_loss_percent": round(len(failed) * 100 / len(known), 2) if len(known) >= 2 else None,
        "latency": None if not latencies else {"current": scans[-1].response_time if scans[-1].status.lower() == "online" else None, "average": round(mean(latencies), 2), "minimum": min(latencies), "maximum": max(latencies)},
        "observations": [{"id": str(row.id), "timestamp": row.scanned_at, "status": row.status, "latency_ms": row.response_time, "source": "Local monitoring", "failure_reason": "No response from this device" if row.status.lower() == "offline" else None} for row in scans],
        "source_status": {"icmp": "available" if scans else "no_data"},
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
