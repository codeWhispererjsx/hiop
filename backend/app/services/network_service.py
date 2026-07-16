from sqlalchemy.orm import Session
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.network.utils import ping_host
from app.models.alert import Alert
from app.models.ticket import Ticket
from app.models.user import User
from app.websocket.connection_manager import manager
from app.services.settings_service import read_network

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

    status_changed = (
        previous_scan is not None
        and previous_scan.status != new_scan.status
    )

    live_event = None

    if status_changed and runtime["automatic_alerts"]:
        alert = Alert(
            device_id=device.id,
            previous_status=previous_scan.status,
            current_status=new_scan.status,
            message=(
                f"{device.hostname} changed from "
                f"{previous_scan.status} to {new_scan.status}"
            )
        )

        db.add(alert)

        live_event = {
            "event": "device_status_changed",
            "device_id": str(device.id),
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "previous_status": previous_scan.status,
            "current_status": new_scan.status
        }

        if new_scan.status == "Offline" and runtime["automatic_offline_tickets"]:
            existing_open_ticket = (
                db.query(Ticket)
                .filter(
                    Ticket.title == f"{device.hostname} is offline",
                    Ticket.status.in_(["Open", "In Progress"])
                )
                .first()
            )

            if not existing_open_ticket:
                admin_user = (
                    db.query(User)
                    .filter(User.role == "admin")
                    .first()
                )

                if admin_user:
                    ticket = Ticket(
                        title=f"{device.hostname} is offline",
                        description=(
                            f"HIOP detected that {device.hostname} "
                            f"at {device.ip_address} changed from "
                            f"{previous_scan.status} to Offline."
                        ),
                        priority="High",
                        status="Open",
                        reported_by=admin_user.id,
                        assigned_to=None,
                        device_id=device.id,
                    )

                    db.add(ticket)

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
