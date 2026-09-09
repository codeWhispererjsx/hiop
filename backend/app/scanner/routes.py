from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.core.tenant import property_context
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.user import User
from app.schemas.network_scan import NetworkScanCreate, NetworkScanResponse, NetworkRangeScan
from app.network.utils import scan_range
from typing import List
from ipaddress import ip_address, ip_network
from app.services.network_service import queue_agent_scan_all_devices, scan_single_device
from app.services.settings_service import read_network
from app.discovery.network import parse_networks


router = APIRouter(
    prefix="/network",
    tags=["Network Scanner"]
)


@router.post("/scan")
def scan_device(
    scan_data: NetworkScanCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    ),
    property_id=Depends(property_context),
):
    device = db.query(Device).filter(
        Device.id == scan_data.device_id,
        Device.property_id == property_id if property_id else True,
    ).first()

    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found"
        )

    approved = parse_networks(read_network(db)["approved_network"])
    if not any(ip_address(device.ip_address) in network for network in approved):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Device IP address is outside the approved private network",
        )

    return scan_single_device(db, device, prefer_agent=True, actor_id=current_user.id)

@router.post("/scan-range")
def scan_network(
    scan: NetworkRangeScan,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    )
):
    approved = parse_networks(read_network(db)["approved_network"])
    requested = ip_network(scan.network, strict=False)
    if not any(requested.subnet_of(network) for network in approved):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Scan range must be inside an approved private network")
    return scan_range(scan.network)


@router.get(
    "/history",
    response_model=List[NetworkScanResponse]
)
def get_scan_history(
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    property_id=Depends(property_context),
):
    query = db.query(NetworkScan).join(Device, NetworkScan.device_id == Device.id)
    if property_id:
        query = query.filter(Device.property_id == property_id)
    scans = query.order_by(NetworkScan.scanned_at.desc()).limit(limit).all()

    return scans


@router.post("/scan-all")
def scan_all(
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    ),
    property_id=Depends(property_context),
):
    return queue_agent_scan_all_devices(db, property_id=property_id, actor_id=current_user.id)
