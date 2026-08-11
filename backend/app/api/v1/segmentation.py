"""V3C cached, read-only VLAN and segmentation APIs."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.services.segmentation_service import SegmentationService

router = APIRouter(prefix="/segmentation", tags=["V3C VLAN Segmentation Intelligence"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
admin = require_roles(["admin"])


@router.get("/vlans")
def list_vlans(search: str | None = Query(None, max_length=100), vlan_id: int | None = Query(None, ge=1, le=4094), subnet: str | None = None, switch: str | None = None, port: str | None = None, db: Session = Depends(get_db), _=Depends(reader)):
    return SegmentationService(db).list_vlans(search, vlan_id, subnet, switch, port)


@router.get("/vlans/{vlan_record_id}")
def vlan_details(vlan_record_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return SegmentationService(db).vlan_details(vlan_record_id)


@router.get("/vlans/{vlan_record_id}/devices")
def vlan_devices(vlan_record_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    details = SegmentationService(db).vlan_details(vlan_record_id)
    return {"items":[x for x in details["memberships"] if x["device"] and x["state"] == "current"]}


@router.get("/vlans/{vlan_record_id}/interfaces")
def vlan_interfaces(vlan_record_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    details = SegmentationService(db).vlan_details(vlan_record_id)
    return {"items":[x for x in details["memberships"] if x["state"] == "current"]}


@router.get("/devices/{device_id}")
def device_vlan(device_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return SegmentationService(db).device_vlan(device_id)


@router.get("/subnets")
def subnets(db: Session = Depends(get_db), _=Depends(reader)):
    rows = SegmentationService(db).list_vlans()["items"]
    return {"items":[{"vlan_id":x["vlan_id"],"vlan_name":x["name"],"subnet":x["subnet"],"gateway":x["gateway"],"evidence":x["source"]} for x in rows if x["subnet"]]}


@router.get("/stats")
def stats(db: Session = Depends(get_db), _=Depends(reader)):
    return SegmentationService(db).stats()


@router.post("/switches/{device_id}/refresh")
def refresh(device_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return SegmentationService(db).refresh(device_id, actor)
