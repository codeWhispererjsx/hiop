from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import IntegrityError

from app.models.asset_intelligence import AssetLifecycleEvent, ManagedAsset
from app.models.asset_management import Vendor
from app.models.alert import Alert
from app.models.device import Device
from app.models.incidents import OperationalIncidentSource
from app.models.network_scan import NetworkScan
from app.models.port_intelligence import PortDeviceAssociation
from app.models.procurement import AssetProcurement, ProcurementAssetLink
from app.models.segmentation import VLANMembershipObservation
from app.models.topology import TopologyLink, TopologyNode
from app.schemas.asset_intelligence import AssetCreate, AssetUpdate, LifecycleTransition
from app.services.audit_service import create_audit_log


def _next_number(db):
    return f"HIOP-{int(db.scalar(text("SELECT nextval('managed_asset_number_seq')"))):06d}"


def _health(status):
    return "Unknown" if not status else "Healthy" if status.lower() == "online" else "Unhealthy" if status.lower() == "offline" else "Unknown"


def _latest_scan(db, device_id):
    if not device_id: return None
    return db.scalar(select(NetworkScan).where(NetworkScan.device_id == device_id).order_by(NetworkScan.scanned_at.desc()).limit(1))


def _relationships(db, asset):
    if not asset.device_id: return {"topology": 0, "ports": 0, "vlans": 0, "alerts": 0, "incidents": 0}
    node_ids = list(db.scalars(select(TopologyNode.id).where(TopologyNode.device_id == asset.device_id)))
    topology = 0 if not node_ids else db.scalar(select(func.count(TopologyLink.id)).where(or_(TopologyLink.source_node_id.in_(node_ids), TopologyLink.target_node_id.in_(node_ids)))) or 0
    ports = db.scalar(select(func.count(PortDeviceAssociation.id)).where(PortDeviceAssociation.connected_device_id == asset.device_id, PortDeviceAssociation.is_current.is_(True))) or 0
    vlans = db.scalar(select(func.count(VLANMembershipObservation.id)).where(VLANMembershipObservation.connected_device_id == asset.device_id, VLANMembershipObservation.is_current.is_(True))) or 0
    alerts = db.scalar(select(func.count(Alert.id)).where(Alert.device_id == asset.device_id)) or 0
    incidents = db.scalar(select(func.count(OperationalIncidentSource.id)).where(OperationalIncidentSource.source_entity_type == "device", OperationalIncidentSource.source_entity_id == asset.device_id)) or 0
    return {"topology": topology, "ports": ports, "vlans": vlans, "alerts": alerts, "incidents": incidents}


def present(db, asset, include_relationships=False):
    device = db.get(Device, asset.device_id) if asset.device_id else None
    scan = _latest_scan(db, asset.device_id)
    history=db.scalars(select(AssetLifecycleEvent).where(AssetLifecycleEvent.asset_id==asset.id,AssetLifecycleEvent.organization_id==asset.organization_id).order_by(AssetLifecycleEvent.created_at.desc())).all() if include_relationships else []
    today=date.today();warranty_status="unknown"
    if asset.warranty_end:warranty_status="active" if asset.warranty_end>=today and (not asset.warranty_start or asset.warranty_start<=today) else "expired" if asset.warranty_end<today else "not_started"
    age_months=None
    if asset.acquisition_date:age_months=max(0,(today.year-asset.acquisition_date.year)*12+today.month-asset.acquisition_date.month-(today.day<asset.acquisition_date.day))
    acquisition=db.execute(select(AssetProcurement).join(ProcurementAssetLink,ProcurementAssetLink.procurement_id==AssetProcurement.id).where(ProcurementAssetLink.asset_id==asset.id)).scalar_one_or_none()
    supplier=db.get(Vendor,asset.vendor_id) if asset.vendor_id else None
    return {
        "id": asset.id, "asset_number": asset.asset_number, "device_id": asset.device_id,
        "name": asset.name, "asset_tag": asset.asset_tag, "device_type": device.device_type if device else asset.device_type,
        "status": asset.status, "ci_category": asset.ci_category,
        "vendor": device.brand if device else asset.vendor, "supplier":{"id":supplier.id,"vendor_id":supplier.vendor_number,"name":supplier.legal_name,"status":supplier.status,"primary_email":supplier.primary_email,"primary_phone":supplier.primary_phone} if supplier else None, "model": device.model if device else asset.model,
        "serial_number": device.serial_number if device else asset.serial_number,
        "hostname": device.hostname if device else None, "ip_address": device.ip_address if device else None,
        "mac_address": device.mac_address if device else None,
        "department_id": asset.department_id or (device.department_id if device else None),
        "department": asset.department_name or (device.department if device else None),
        "room_id": asset.room_id or (device.room_id if device else None), "location": asset.location_name or (device.location if device else None),
        "business_owner": asset.business_owner, "technical_owner": asset.technical_owner,
        "description": asset.description or (device.description if device else None), "source": asset.source,
        "condition":asset.condition,"acquisition_date":asset.acquisition_date,"received_date":asset.received_date,"deployment_date":asset.deployment_date,
        "retirement_date":asset.retirement_date,"retirement_reason":asset.retirement_reason,"warranty_start":asset.warranty_start,"warranty_end":asset.warranty_end,
        "expected_replacement_date":asset.expected_replacement_date,"lifecycle_notes":asset.lifecycle_notes,"warranty_status":warranty_status,"asset_age_months":age_months,
        "lifecycle_history":history,
        "acquisition":{"id":acquisition.id,"procurement_number":acquisition.procurement_number,"title":acquisition.title} if acquisition else None,
        "field_sources": asset.field_sources, "health": _health(scan.status if scan else None),
        "last_seen": scan.scanned_at if scan else None,
        "relationships": _relationships(db, asset) if include_relationships else {},
        "created_at": asset.created_at, "updated_at": asset.updated_at,
    }


def ensure_asset_for_device(db, device, actor, organization_id=None):
    existing = db.scalar(select(ManagedAsset).where(ManagedAsset.device_id == device.id))
    if existing: return existing
    organization_id=organization_id or actor.organization_id
    if not organization_id: raise HTTPException(403,"Organization context is required")
    asset = ManagedAsset(asset_number=_next_number(db), organization_id=organization_id, device_id=device.id, name=device.hostname,
        asset_tag=device.asset_tag or None, device_type=device.device_type, status="retired" if device.inventory_status == "Retired" else "active",
        ci_category="network" if device.device_type.lower() in {"switch","router","firewall","access point","network appliance"} else "server" if device.device_type.lower()=="server" else "device",
        department_id=device.department_id, department_name=device.department or None, room_id=device.room_id, location_name=device.location or None,
        description=device.description, source="discovery" if device.mac_address else "manual", field_sources={"technical_identity":"Device","organizational_metadata":"Imported from existing inventory"}, created_by=str(actor.id), updated_by=str(actor.id))
    db.add(asset);db.flush()
    create_audit_log(db,actor.username,"ASSET_CREATED","ManagedAsset",str(asset.id),f"Created {asset.asset_number} for existing device {device.id}")
    return asset


def create_asset(db, payload: AssetCreate, actor, organization_id=None):
    organization_id=organization_id or actor.organization_id
    if not organization_id: raise HTTPException(403,"Organization context is required")
    _validate_dates(payload.model_dump(exclude_unset=True))
    asset=ManagedAsset(asset_number=_next_number(db),organization_id=organization_id,created_by=str(actor.id),updated_by=str(actor.id),source="manual",field_sources={"organizational_metadata":"Manual"},**payload.model_dump())
    db.add(asset)
    try:
        db.flush();db.add(AssetLifecycleEvent(asset_id=asset.id,organization_id=organization_id,previous_status=None,new_status=asset.status,reason="Asset created",changed_by=str(actor.id),changed_by_name=actor.username));create_audit_log(db,actor.username,"ASSET_LIFECYCLE_CREATED","ManagedAsset",str(asset.id),f"Created manual asset {asset.asset_number} in {asset.status}");db.commit();db.refresh(asset)
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,"Asset tag already exists") from exc
    return asset


def update_asset(db, asset, payload: AssetUpdate, actor):
    _validate_dates(payload.model_dump(exclude_unset=True),asset)
    changes=[]
    for key,value in payload.model_dump(exclude_unset=True).items():
        old=getattr(asset,key)
        if old!=value: changes.append(f"{key}: {old or 'Unknown'} -> {value or 'Unknown'}");setattr(asset,key,value)
    if asset.device_id and "asset_tag" in payload.model_fields_set:
        device=db.get(Device,asset.device_id);device.asset_tag=asset.asset_tag or device.asset_tag
    asset.updated_by=str(actor.id);asset.updated_at=datetime.now(timezone.utc);asset.field_sources={**asset.field_sources,**{key:"Manual" for key in payload.model_fields_set}}
    try:
        create_audit_log(db,actor.username,"ASSET_UPDATED","ManagedAsset",str(asset.id),"; ".join(changes) or "No material changes")
        actions={"status":"ASSET_STATUS_CHANGED","asset_tag":"ASSET_TAG_CHANGED","department_id":"ASSET_DEPARTMENT_CHANGED","department_name":"ASSET_DEPARTMENT_CHANGED","room_id":"ASSET_LOCATION_CHANGED","location_name":"ASSET_LOCATION_CHANGED","business_owner":"ASSET_OWNER_CHANGED","technical_owner":"ASSET_TECHNICAL_OWNER_CHANGED","condition":"ASSET_CONDITION_CHANGED","warranty_start":"ASSET_WARRANTY_CHANGED","warranty_end":"ASSET_WARRANTY_CHANGED","expected_replacement_date":"ASSET_EXPECTED_REPLACEMENT_CHANGED"}
        for field in payload.model_fields_set:
            if field in actions:create_audit_log(db,actor.username,actions[field],"ManagedAsset",str(asset.id),next((item for item in changes if item.startswith(field+":")),f"{field} reviewed"))
        db.commit();db.refresh(asset)
    except IntegrityError as exc:
        db.rollback();raise HTTPException(409,"Asset tag already exists") from exc
    return asset


TRANSITIONS={"planned":{"received"},"received":{"deployed"},"deployed":{"active"},"active":{"in_maintenance","retired"},"in_maintenance":{"active","retired"},"retired":{"active"}}


def _validate_dates(values,asset=None):
    get=lambda key:values.get(key,getattr(asset,key,None) if asset else None)
    acquisition,received,deployed,warranty_start,warranty_end=get("acquisition_date"),get("received_date"),get("deployment_date"),get("warranty_start"),get("warranty_end")
    if acquisition and received and received<acquisition:raise HTTPException(422,"Received date cannot be before acquisition date")
    if received and deployed and deployed<received:raise HTTPException(422,"Deployment date cannot be before received date")
    if warranty_start and warranty_end and warranty_end<warranty_start:raise HTTPException(422,"Warranty end cannot be before warranty start")


def transition_asset(db,asset,payload:LifecycleTransition,actor):
    previous=asset.status
    if payload.status==previous:raise HTTPException(409,"Asset is already in this lifecycle state")
    if payload.status not in TRANSITIONS.get(previous,set()):raise HTTPException(422,f"Lifecycle transition {previous} to {payload.status} is not allowed")
    if payload.status=="retired" and not payload.reason:raise HTTPException(422,"Retirement reason is required")
    asset.status=payload.status;asset.updated_by=str(actor.id);asset.updated_at=datetime.now(timezone.utc)
    if payload.status=="retired":asset.retirement_date=date.today();asset.retirement_reason=payload.reason;asset.retired_by=str(actor.id)
    elif previous=="retired":asset.retirement_date=None;asset.retirement_reason=None;asset.retired_by=None
    event=AssetLifecycleEvent(asset_id=asset.id,organization_id=asset.organization_id,previous_status=previous,new_status=payload.status,reason=payload.reason,notes=payload.notes,changed_by=str(actor.id),changed_by_name=actor.username);db.add(event)
    action={"received":"ASSET_RECEIVED","deployed":"ASSET_DEPLOYED","active":"ASSET_REACTIVATED" if previous=="retired" else "ASSET_ACTIVATED","in_maintenance":"ASSET_ENTERED_MAINTENANCE","retired":"ASSET_RETIRED"}[payload.status]
    create_audit_log(db,actor.username,action,"ManagedAsset",str(asset.id),f"{previous} -> {payload.status}"+(f"; {payload.reason}" if payload.reason else ""));db.commit();db.refresh(asset);return asset


def list_assets(db, search=None, status=None, device_type=None, department=None, location=None, health=None, vendor=None, organization_id=None):
    query=select(ManagedAsset)
    if organization_id:query=query.where(ManagedAsset.organization_id==organization_id)
    rows=db.scalars(query.order_by(ManagedAsset.asset_number)).all();items=[present(db,row) for row in rows]
    def match(item):
        values=[item.get(k) for k in ("asset_number","asset_tag","name","hostname","ip_address","mac_address","serial_number")]
        return (not search or any(search.casefold() in str(x).casefold() for x in values if x)) and (not status or item["status"]==status) and (not device_type or item["device_type"].casefold()==device_type.casefold()) and (not department or (item["department"] or "").casefold()==department.casefold()) and (not location or (item["location"] or "").casefold()==location.casefold()) and (not health or item["health"].casefold()==health.casefold()) and (not vendor or (item["vendor"] or "").casefold()==vendor.casefold())
    return [item for item in items if match(item)]
