from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.core.tenant import organization_context, device_in_organization
from app.models.device import Device
from app.services.monitoring_health_service import WINDOWS, device_health, summary

router = APIRouter(prefix="/monitoring", tags=["V3D Monitoring Health"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
operator = require_roles(["admin", "technician"])

@router.get("/summary")
def monitoring_summary(window: str = Query("24h"), db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context)):
    if window not in WINDOWS: raise HTTPException(422, "Unsupported monitoring window")
    return summary(db, window,organization_id)

@router.get("/devices/{device_id}")
def monitoring_device(device_id: UUID, window: str = Query("24h"), db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context)):
    if window not in WINDOWS: raise HTTPException(422, "Unsupported monitoring window")
    device = device_in_organization(db,device_id,organization_id)
    if not device: raise HTTPException(404, "Device not found")
    return device_health(db, device, window)
