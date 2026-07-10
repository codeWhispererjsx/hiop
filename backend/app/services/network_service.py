from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.network.utils import ping_host


def scan_single_device(
    db: Session,
    device: Device
):
    result = ping_host(device.ip_address)

    scan = NetworkScan(
        device_id=device.id,
        ip_address=device.ip_address,
        status=result["status"],
        response_time=result["response_time"]
    )

    db.add(scan)
    db.commit()
    db.refresh(scan)

    return scan

def scan_all_devices(db: Session):
    devices = db.query(Device).all()
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