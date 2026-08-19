from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.core.tenant import organization_context, property_context
from app.models.hierarchy import Property
from app.models.device import Device
from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.network_scan import NetworkScan
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.device import (
    DeviceCreate,
    DeviceResponse,
    DeviceUpdate,
)
from app.schemas.history import AlertResponse, AuditLogResponse
from app.schemas.network_scan import NetworkScanResponse
from app.schemas.ticket import TicketResponse
from app.services.device_service import (
    create_device as create_device_service,
    update_device as update_device_service,
    delete_device as delete_device_service,
)


class PaginatedDeviceResponse(BaseModel):
    items: List[DeviceResponse]
    total: int
    page: int
    page_size: int
    total_pages: int

router = APIRouter(
    prefix="/devices",
    tags=["Devices"]
)
from app.services.billing_service import enforce_limit


def require_device(db: Session, device_id: str, organization_id) -> Device:
    device = db.query(Device).join(Property,Device.property_id==Property.id).filter(Device.id == device_id,Property.organization_id==organization_id).first()
    if not device:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.post("/", response_model=DeviceResponse)
def create_device(
    device: DeviceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])),
    organization_id=Depends(organization_context),
):
    enforce_limit(db,organization_id,"devices")
    if device.property_id and not db.query(Property).filter(Property.id==device.property_id,Property.organization_id==organization_id).first(): raise HTTPException(403,"Property is outside your organization")
    return create_device_service(
        db=db,
        device=device,
        current_user=current_user
    )


@router.get("/", response_model=PaginatedDeviceResponse)
def get_devices(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization_id=Depends(organization_context),
    property_id=Depends(property_context),
):
    # Apply organization scope first (pagination security)
    query=db.query(Device).join(Property,Device.property_id==Property.id).filter(Property.organization_id==organization_id)
    if property_id:query=query.filter(Device.property_id==property_id)
    
    # Get total count
    total = query.count()
    
    # Calculate pagination
    total_pages = (total + page_size - 1) // page_size
    offset = (page - 1) * page_size
    
    # Apply pagination
    devices = query.offset(offset).limit(page_size).all()
    
    return {
        "items": devices,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.put("/{device_id}", response_model=DeviceResponse)
def update_device(
    device_id: str,
    device_data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(
        require_roles(["admin", "technician"])
    ), organization_id=Depends(organization_context)
):
    require_device(db,device_id,organization_id)
    return update_device_service(
        db=db,
        device_id=device_id,
        device_data=device_data,
        current_user=current_user
    )


@router.delete("/{device_id}")
def delete_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin"])), organization_id=Depends(organization_context)
):
    require_device(db,device_id,organization_id)
    return delete_device_service(
        db=db,
        device_id=device_id,
        current_user=current_user
    )

@router.get("/{device_id}", response_model=DeviceResponse)
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), organization_id=Depends(organization_context)
):
    return require_device(db, device_id,organization_id)


@router.get("/{device_id}/scans", response_model=List[NetworkScanResponse])
def get_device_scans(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), organization_id=Depends(organization_context),
):
    require_device(db, device_id,organization_id)
    return db.query(NetworkScan).filter(NetworkScan.device_id == device_id).order_by(NetworkScan.scanned_at.desc()).all()


@router.get("/{device_id}/alerts", response_model=List[AlertResponse])
def get_device_alerts(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), organization_id=Depends(organization_context),
):
    require_device(db, device_id,organization_id)
    return db.query(Alert).filter(Alert.device_id == device_id).order_by(Alert.created_at.desc()).all()


@router.get("/{device_id}/tickets", response_model=List[TicketResponse])
def get_device_tickets(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user), organization_id=Depends(organization_context),
):
    require_device(db, device_id,organization_id)
    return db.query(Ticket).filter(Ticket.device_id == device_id).order_by(Ticket.created_at.desc()).all()


@router.get("/{device_id}/audit-logs", response_model=List[AuditLogResponse])
def get_device_audit_logs(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])), organization_id=Depends(organization_context),
):
    require_device(db, device_id,organization_id)
    return db.query(AuditLog).filter(
        AuditLog.entity_type == "Device",
        AuditLog.entity_id == device_id,
    ).order_by(AuditLog.created_at.desc()).all()
