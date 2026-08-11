"""V3B cached, observational switch and port intelligence APIs."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.services.port_intelligence_service import PortIntelligenceService

router = APIRouter(prefix="/port-intelligence", tags=["V3B Switch and Port Intelligence"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
admin = require_roles(["admin"])


@router.get("/devices/{device_id}/connection")
def device_connection(device_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return PortIntelligenceService(db).device_connection(device_id)


@router.get("/switches/{device_id}/interfaces")
def switch_interfaces(
    device_id: UUID,
    search: str | None = Query(default=None, max_length=100),
    status: str | None = Query(default=None, pattern="^(active)?$"),
    endpoint: str | None = Query(default=None, pattern="^(unknown)?$"),
    db: Session = Depends(get_db), _=Depends(reader),
):
    return PortIntelligenceService(db).switch_interfaces(device_id, search, status, endpoint)


@router.get("/interfaces/{interface_id}")
def interface_details(interface_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return PortIntelligenceService(db).interface(interface_id)


@router.post("/switches/{device_id}/refresh")
def refresh_switch(device_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return PortIntelligenceService(db).refresh(device_id, actor)


@router.get("/stats")
def port_stats(db: Session = Depends(get_db), _=Depends(reader)):
    return PortIntelligenceService(db).stats()
