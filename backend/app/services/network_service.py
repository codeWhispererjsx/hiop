import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from app.models.device import Device
from app.models.local_agent import AgentJob, LocalAgentRegistration
from app.models.network_scan import NetworkScan
from app.network.utils import ping_host
from app.websocket.connection_manager import manager
from app.services.settings_service import read_network
from app.services.automation_event_outbox_service import publish_internal_event


def _online_agent_for_property(db: Session, property_id):
    if not property_id:
        return None
    return (
        db.query(LocalAgentRegistration)
        .filter(
            LocalAgentRegistration.property_id == property_id,
            LocalAgentRegistration.revoked_at.is_(None),
            LocalAgentRegistration.retired_at.is_(None),
            LocalAgentRegistration.last_heartbeat >= datetime.now(timezone.utc) - timedelta(seconds=120),
        )
        .order_by(LocalAgentRegistration.last_heartbeat.desc())
        .first()
    )


def queue_agent_scan(db: Session, device: Device, actor_id=None):
    runtime = read_network(db)
    agent = _online_agent_for_property(db, device.property_id)
    if not agent:
        return None
    row = AgentJob(
        agent_id=agent.id,
        organization_id=agent.organization_id,
        property_id=agent.property_id,
        job_type="MONITORING",
        payload=json.dumps(
            {
                "device_id": str(device.id),
                "target": device.ip_address,
                "timeout": runtime["ping_timeout_seconds"],
            },
            separators=(",", ":"),
        ),
        timeout_seconds=max(10, int(runtime["ping_timeout_seconds"]) + 10),
        created_by=actor_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

def scan_single_device(
    db: Session,
    device: Device,
    *,
    prefer_agent: bool = False,
    actor_id=None,
):
    if prefer_agent:
        queued = queue_agent_scan(db, device, actor_id)
        if queued:
            return {
                "queued": True,
                "job_id": str(queued.id),
                "device_id": str(device.id),
                "ip_address": device.ip_address,
                "status": "queued",
                "response_time": None,
            }

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


def queue_agent_scan_all_devices(db: Session, *, property_id=None, actor_id=None):
    query = db.query(Device).filter(Device.inventory_status != "Retired")
    if property_id:
        query = query.filter(Device.property_id == property_id)
    devices = [device for device in query.all() if device.ip_address]
    queued = []
    immediate = []
    for device in devices:
        job = queue_agent_scan(db, device, actor_id)
        if job:
            queued.append(
                {
                    "device_id": str(device.id),
                    "ip_address": device.ip_address,
                    "status": "queued",
                    "job_id": str(job.id),
                    "response_time": None,
                }
            )
        else:
            immediate.append(scan_single_device(db, device))
    return {
        "total_devices": len(devices),
        "queued": len(queued),
        "online": 0,
        "offline": 0,
        "results": queued + [
            {
                "device_id": str(scan.device_id),
                "ip_address": scan.ip_address,
                "status": scan.status,
                "response_time": scan.response_time,
            }
            for scan in immediate
        ],
    }
