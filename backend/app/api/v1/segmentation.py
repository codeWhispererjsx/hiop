"""V3C cached, read-only VLAN and segmentation APIs."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context, property_context
from app.services.segmentation_service import SegmentationService

router = APIRouter(prefix="/segmentation", tags=["V3C VLAN Segmentation Intelligence"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
admin = require_roles(["admin"])


@router.get("/vlans")
def list_vlans(search: str | None = Query(None, max_length=100), vlan_id: int | None = Query(None, ge=1, le=4094), subnet: str | None = None, switch: str | None = None, port: str | None = None, db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    return SegmentationService(db,organization_id=organization_id,property_id=property_id).list_vlans(search, vlan_id, subnet, switch, port)


@router.get("/vlans/{vlan_record_id}")
def vlan_details(vlan_record_id: UUID, db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    return SegmentationService(db,organization_id=organization_id,property_id=property_id).vlan_details(vlan_record_id)


@router.get("/vlans/{vlan_record_id}/devices")
def vlan_devices(vlan_record_id: UUID, db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    details = SegmentationService(db,organization_id=organization_id,property_id=property_id).vlan_details(vlan_record_id)
    return {"items":[x for x in details["memberships"] if x["device"] and x["state"] == "current"]}


@router.get("/vlans/{vlan_record_id}/interfaces")
def vlan_interfaces(vlan_record_id: UUID, db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    details = SegmentationService(db,organization_id=organization_id,property_id=property_id).vlan_details(vlan_record_id)
    return {"items":[x for x in details["memberships"] if x["state"] == "current"]}


@router.get("/devices/{device_id}")
def device_vlan(device_id: UUID, db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    return SegmentationService(db,organization_id=organization_id,property_id=property_id).device_vlan(device_id)


@router.get("/subnets")
def subnets(db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    rows = SegmentationService(db,organization_id=organization_id,property_id=property_id).list_vlans()["items"]
    return {"items":[{"vlan_id":x["vlan_id"],"vlan_name":x["name"],"subnet":x["subnet"],"gateway":x["gateway"],"evidence":x["source"]} for x in rows if x["subnet"]]}


@router.get("/stats")
def stats(db: Session = Depends(get_db), _=Depends(reader),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    return SegmentationService(db,organization_id=organization_id,property_id=property_id).stats()


@router.post("/switches/{device_id}/refresh")
def refresh(device_id: UUID, db: Session = Depends(get_db), actor=Depends(admin),organization_id=Depends(organization_context),property_id=Depends(property_context)):
    return SegmentationService(db,organization_id=organization_id,property_id=property_id).refresh(device_id, actor)
