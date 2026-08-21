from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from typing import List
from uuid import UUID

from app.api.dependencies import get_db
from app.core.security import get_current_user, require_roles
from app.core.tenant import organization_context, property_context
from app.models.discovered_device import DiscoveredDevice, ReviewStatus
from app.models.hierarchy import Property
from app.models.user import User
from app.services.audit_service import create_audit_log

router = APIRouter(
    prefix="/discovery",
    tags=["Discovery"]
)


class DiscoveryFilters:
    def __init__(self, skip: int = 0, limit: int = 50, status: str | None = None, review_status: str | None = None, search: str | None = None):
        self.skip = skip
        self.limit = limit
        self.status = status
        self.review_status = review_status
        self.search = search


@router.get("")
def get_discovered_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    status: str | None = None,
    review_status: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization_id=Depends(organization_context),
    property_id=Depends(property_context),
):
    """Get paginated list of discovered devices"""
    query = db.query(DiscoveredDevice)
    
    if search:
        query = query.filter(
            or_(
                DiscoveredDevice.ip_address.ilike(f"%{search}%"),
                DiscoveredDevice.hostname.ilike(f"%{search}%"),
                DiscoveredDevice.mac_address.ilike(f"%{search}%"),
                DiscoveredDevice.vendor.ilike(f"%{search}%"),
            )
        )
    
    if status:
        query = query.filter(DiscoveredDevice.status == status)
    
    if review_status:
        query = query.filter(DiscoveredDevice.review_status == review_status)
    
    total = query.count()
    items = query.order_by(desc(DiscoveredDevice.last_seen_at)).offset(skip).limit(limit).all()
    
    pages = (total + limit - 1) // limit
    
    return {
        "items": items,
        "total": total,
        "page": skip // limit + 1,
        "page_size": limit,
        "pages": pages
    }


@router.get("/stats")
def get_discovery_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    organization_id=Depends(organization_context),
):
    """Get discovery statistics"""
    total = db.query(DiscoveredDevice).count()
    pending = db.query(DiscoveredDevice).filter(DiscoveredDevice.review_status == ReviewStatus.PENDING).count()
    approved = db.query(DiscoveredDevice).filter(DiscoveredDevice.review_status == ReviewStatus.APPROVED).count()
    ignored = db.query(DiscoveredDevice).filter(DiscoveredDevice.review_status == ReviewStatus.IGNORED).count()
    rejected = db.query(DiscoveredDevice).filter(DiscoveredDevice.review_status == ReviewStatus.REJECTED).count()
    
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "ignored": ignored,
        "rejected": rejected
    }


@router.get("/{device_id}")
def get_discovered_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a specific discovered device"""
    try:
        device_uuid = UUID(device_id)
        device = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == device_uuid).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        return device
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID")


@router.post("/run")
def run_discovery(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])),
    organization_id=Depends(organization_context),
):
    """Run a discovery scan"""
    range_scanned = body.get("range_scanned")
    if not range_scanned:
        raise HTTPException(status_code=400, detail="range_scanned is required")
    
    # This is a placeholder - actual discovery would be implemented in DiscoveryService
    create_audit_log(db, current_user.username, "DISCOVERY_RUN", "DiscoveryRun", str(range_scanned), f"Started discovery scan on {range_scanned}")
    db.commit()
    
    return {
        "id": "pending",
        "status": "pending",
        "range_scanned": range_scanned,
        "started_at": "2026-08-17T00:00:00Z",
        "devices_found": 0
    }


@router.post("/{device_id}/approve")
def approve_discovery(
    device_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])),
    organization_id=Depends(organization_context),
):
    """Approve a discovered device"""
    try:
        device_uuid = UUID(device_id)
        device = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == device_uuid).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        device.review_status = ReviewStatus.APPROVED
        device.reviewed_by = current_user.id
        device.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        
        create_audit_log(db, current_user.username, "DISCOVERY_APPROVE", "DiscoveredDevice", device_id, f"Approved discovered device {device.ip_address}")
        db.commit()
        db.refresh(device)
        
        return device
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID")


@router.post("/{device_id}/ignore")
def ignore_discovery(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])),
    organization_id=Depends(organization_context),
):
    """Ignore a discovered device"""
    try:
        device_uuid = UUID(device_id)
        device = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == device_uuid).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        device.review_status = ReviewStatus.IGNORED
        device.reviewed_by = current_user.id
        device.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        
        create_audit_log(db, current_user.username, "DISCOVERY_IGNORE", "DiscoveredDevice", device_id, f"Ignored discovered device {device.ip_address}")
        db.commit()
        db.refresh(device)
        
        return device
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID")


@router.post("/{device_id}/reject")
def reject_discovery(
    device_id: str,
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])),
    organization_id=Depends(organization_context),
):
    """Reject a discovered device"""
    try:
        device_uuid = UUID(device_id)
        device = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == device_uuid).first()
        if not device:
            raise HTTPException(status_code=404, detail="Device not found")
        
        device.review_status = ReviewStatus.REJECTED
        device.reviewed_by = current_user.id
        device.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        device.notes = body.get("reason", "")
        
        create_audit_log(db, current_user.username, "DISCOVERY_REJECT", "DiscoveredDevice", device_id, f"Rejected discovered device {device.ip_address}")
        db.commit()
        db.refresh(device)
        
        return device
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid device ID")


@router.post("/bulk-approve")
def bulk_approve_discovery(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])),
    organization_id=Depends(organization_context),
):
    """Bulk approve discovered devices"""
    items = body.get("items", [])
    if not items:
        raise HTTPException(status_code=400, detail="items is required")
    
    succeeded = 0
    failed = 0
    
    for item in items:
        try:
            device_id = item.get("id")
            device_uuid = UUID(device_id)
            device = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == device_uuid).first()
            if device:
                device.review_status = ReviewStatus.APPROVED
                device.reviewed_by = current_user.id
                device.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                succeeded += 1
        except:
            failed += 1
    
    db.commit()
    create_audit_log(db, current_user.username, "DISCOVERY_BULK_APPROVE", "DiscoveredDevice", "multiple", f"Bulk approved {succeeded} devices")
    
    return {"succeeded": succeeded, "failed": failed}


@router.post("/bulk-ignore")
def bulk_ignore_discovery(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])),
    organization_id=Depends(organization_context),
):
    """Bulk ignore discovered devices"""
    ids = body.get("discovery_ids", [])
    if not ids:
        raise HTTPException(status_code=400, detail="discovery_ids is required")
    
    succeeded = 0
    failed = 0
    
    for device_id in ids:
        try:
            device_uuid = UUID(device_id)
            device = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == device_uuid).first()
            if device:
                device.review_status = ReviewStatus.IGNORED
                device.reviewed_by = current_user.id
                device.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                succeeded += 1
        except:
            failed += 1
    
    db.commit()
    create_audit_log(db, current_user.username, "DISCOVERY_BULK_IGNORE", "DiscoveredDevice", "multiple", f"Bulk ignored {succeeded} devices")
    
    return {"succeeded": succeeded, "failed": failed}


@router.post("/bulk-reject")
def bulk_reject_discovery(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "technician"])),
    organization_id=Depends(organization_context),
):
    """Bulk reject discovered devices"""
    ids = body.get("discovery_ids", [])
    reason = body.get("reason", "")
    
    if not ids:
        raise HTTPException(status_code=400, detail="discovery_ids is required")
    
    succeeded = 0
    failed = 0
    
    for device_id in ids:
        try:
            device_uuid = UUID(device_id)
            device = db.query(DiscoveredDevice).filter(DiscoveredDevice.id == device_uuid).first()
            if device:
                device.review_status = ReviewStatus.REJECTED
                device.reviewed_by = current_user.id
                device.reviewed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                device.notes = reason
                succeeded += 1
        except:
            failed += 1
    
    db.commit()
    create_audit_log(db, current_user.username, "DISCOVERY_BULK_REJECT", "DiscoveredDevice", "multiple", f"Bulk rejected {succeeded} devices")
    
    return {"succeeded": succeeded, "failed": failed}


@router.get("/export")
def export_discovery(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(["admin", "viewer"])),
    organization_id=Depends(organization_context),
):
    """Export discovered devices as CSV"""
    # Placeholder - would return CSV file
    return {"message": "Export functionality coming soon"}
