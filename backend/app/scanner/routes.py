from fastapi import APIRouter, Depends, HTTPException, status
from ping3 import ping
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import require_roles
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.user import User
from app.schemas.network_scan import NetworkScanCreate, NetworkScanResponse


router = APIRouter(
    prefix="/network",
    tags=["Network Scanner"]
)


@router.post("/scan", response_model=NetworkScanResponse)
def scan_device(
    scan_data: NetworkScanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
):
    device = db.query(Device).filter(
        Device.id == scan_data.device_id
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    response_seconds = ping(
        device.ip_address,
        timeout=2
    )

    if response_seconds is None:
        device_status = "Offline"
        response_time = None
    else:
        device_status = "Online"
        response_time = round(response_seconds * 1000)

    scan_result = NetworkScan(
        device_id=device.id,
        ip_address=device.ip_address,
        status=device_status,
        response_time=response_time
    )

    db.add(scan_result)
    db.commit()
    db.refresh(scan_result)

    return scan_result