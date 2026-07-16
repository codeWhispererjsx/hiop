from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.user import User
from app.schemas.network_scan import NetworkScanCreate, NetworkScanResponse, NetworkRangeScan
from app.network.utils import scan_range
from typing import List
from ipaddress import ip_network
from app.services.network_service import scan_all_devices, scan_single_device
from app.services.settings_service import read_network


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

    return scan_single_device(db, device)

@router.post("/scan-range")
def scan_network(
    scan: NetworkRangeScan,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
):
    approved = ip_network(read_network(db)["approved_network"], strict=False)
    requested = ip_network(scan.network, strict=False)
    if not requested.subnet_of(approved):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scan range must be inside the approved private network")
    return scan_range(scan.network)


@router.get(
    "/history",
    response_model=List[NetworkScanResponse]
)
def get_scan_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    scans = (
        db.query(NetworkScan)
        .order_by(NetworkScan.scanned_at.desc())
        .limit(limit)
        .all()
    )

    return scans


@router.post("/scan-all")
def scan_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
):
    return scan_all_devices(db)
