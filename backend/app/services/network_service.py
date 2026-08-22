from sqlalchemy.orm import Session
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.network.utils import ping_host
from app.websocket.connection_manager import manager
from app.services.settings_service import read_network
from app.services.automation_event_outbox_service import publish_internal_event

def scan_single_device(
    db: Session,
    device: Device
):
    previous_scan = (
        db.query(NetworkScan)
        .filter(NetworkScan.device_id == device.id)
        .order_by(NetworkScan.scanned_at.desc())
        .first()
    )

    runtime = read_network(db)
    result = ping_host(device.ip_address, timeout=runtime["ping_timeout_seconds"])

    new_scan = NetworkScan(
        device_id=device.id,
        ip_address=device.ip_address,
        status=result["status"],
        response_time=result["response_time"]
    )

    db.add(new_scan)
    device.network_status = new_scan.status
    db.flush()
    from app.services.alert_event_service import evaluate_scan
    alert_result = evaluate_scan(db, device, new_scan)

    status_changed = (
        previous_scan is not None
        and previous_scan.status != new_scan.status
    )

    live_event = None

    if status_changed:
        if alert_result["opened"]:
            publish_internal_event(db,event_type="alert_created",property_id=device.property_id,source_entity_type="device",source_entity_id=device.id,safe_payload={"opened":alert_result["opened"]},severity="critical" if new_scan.status=="Offline" else "informational",status="open",correlation_key=f"device:{device.id}:network")
        publish_internal_event(db,event_type="device_offline" if new_scan.status=="Offline" else "device_restored",property_id=device.property_id,source_entity_type="device",source_entity_id=device.id,safe_payload={"automatic_ticket":runtime["automatic_offline_tickets"]},severity="critical" if new_scan.status=="Offline" else "informational",status=new_scan.status.lower(),correlation_key=f"device:{device.id}:network")

        live_event = {
            "event": "device_status_changed",
            "device_id": str(device.id),
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "previous_status": previous_scan.status,
            "current_status": new_scan.status
        }

        # The internal event outbox is the single automatic ticket path. It
        # creates a property-scoped OperationalIncident and deduplicates it by
        # correlation key, so automated work appears in Maintain instead of
        # disappearing into the legacy Ticket table.

    try:
        db.commit()
        db.refresh(new_scan)
    except Exception:
        db.rollback()
        raise

    if live_event:
        manager.broadcast_from_thread(live_event)

    return new_scan


def scan_all_devices(db: Session):
    devices = db.query(Device).filter(Device.inventory_status != "Retired").all()
    results = []

    for device in devices:
        scan = scan_single_device(db, device)

        results.append({
            "device_id": str(device.id),
            "ip_address": device.ip_address,
            "status": scan.status,
            "response_time": scan.response_time
        })

    return {
        "total_devices": len(devices),
        "online": sum(
            1 for result in results
            if result["status"] == "Online"
        ),
        "offline": sum(
            1 for result in results
            if result["status"] == "Offline"
        ),
        "results": results
    }
