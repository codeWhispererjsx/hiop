import secrets
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_

from app.models.asset_intelligence import ManagedAsset
from app.models.alert import Alert
from app.models.asset_management import Vendor, VendorContact
from app.models.device import Device
from app.models.hierarchy import Building, Department, Floor, Property, Room
from app.models.hospitality_operations import DeviceTechnologyService, HospitalityTechnologyService
from app.models.incidents import IncidentImpactAssessment, IncidentTimelineEntry, OperationalIncident, OperationalIncidentSource
from app.models.procurement import AssetProcurement, ProcurementAssetLink
from app.models.service_management import IncidentAssetRelationship, ServiceAssetRelationship
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.multi_property_service import allowed_property_ids


STATUS_MAP = {"declared": "new", "detected": "new", "investigating": "in_progress", "contained": "in_progress", "mitigating": "in_progress", "monitoring": "in_progress", "recovered": "resolved"}
TRANSITIONS = {
    "new": {"acknowledged"},
    "acknowledged": {"in_progress", "on_hold", "resolved"},
    "in_progress": {"on_hold", "resolved"},
    "on_hold": {"in_progress", "resolved"},
    "resolved": {"closed", "in_progress"},
    "closed": {"in_progress"},
}


def status_of(row): return STATUS_MAP.get(row.status, row.status)


def require_property(db, property_id, organization_id):
    row = db.query(Property).filter_by(id=property_id, organization_id=organization_id).first()
    if not row: raise HTTPException(404, "Property not found")
    return row


def require_service(db, service_id, organization_id):
    row = db.query(HospitalityTechnologyService).filter_by(id=service_id, organization_id=organization_id).first()
    if not row: raise HTTPException(404, "Technology service not found")
    return row


def require_incident(db, incident_id, organization_id):
    row = db.query(OperationalIncident).filter_by(id=incident_id, organization_id=organization_id).first()
    if not row: raise HTTPException(404, "Incident not found")
    return row


def require_asset(db, asset_id, organization_id):
    row = db.query(ManagedAsset).filter_by(id=asset_id, organization_id=organization_id).first()
    if not row: raise HTTPException(404, "Asset not found")
    return row


def require_device(db, device_id, organization_id):
    row = db.query(Device).join(Property, Device.property_id == Property.id).filter(Device.id == device_id, Property.organization_id == organization_id).first()
    if not row: raise HTTPException(404, "Device not found")
    return row


def require_user(db, user_id, organization_id):
    row = db.query(User).filter_by(id=user_id, organization_id=organization_id).first()
    if not row: raise HTTPException(404, "Organization user not found")
    return row


def require_eligible_technician(db, user_id, organization_id, property_id):
    row = db.query(User).filter_by(id=user_id, organization_id=organization_id, role="technician", is_active=True).first()
    if not row:
        raise HTTPException(422, "Select an active IT Technician from this organization")
    if property_id not in allowed_property_ids(db, row):
        raise HTTPException(422, "This technician does not have access to the ticket property")
    return row


def eligible_technicians(db, organization_id, property_id):
    require_property(db, property_id, organization_id)
    technicians = db.query(User).filter_by(organization_id=organization_id, role="technician", is_active=True).order_by(User.username).all()
    return [{"id": technician.id, "username": technician.username} for technician in technicians if property_id in allowed_property_ids(db, technician)]


def timeline(db, incident, actor, entry_type, title, summary=None):
    row = IncidentTimelineEntry(incident_id=incident.id, property_id=incident.property_id, entry_type=entry_type, title=title, summary=summary, actor_user_id=actor.username)
    db.add(row)
    return row


def audit(db, actor, action, entity, entity_id, description):
    create_audit_log(db, actor.username, action, entity, str(entity_id), description)


def create_service(db, payload, actor, organization_id):
    require_property(db, payload.property_id, organization_id)
    if payload.owner_user_id: require_user(db, payload.owner_user_id, organization_id)
    if payload.department_id and not db.query(Department).filter_by(id=payload.department_id, organization_id=organization_id).first(): raise HTTPException(422, "Department does not belong to this organization")
    duplicate = db.query(HospitalityTechnologyService).filter_by(property_id=payload.property_id, code=payload.code).first()
    if duplicate: raise HTTPException(409, "A service with this code already exists for the property")
    row = HospitalityTechnologyService(organization_id=organization_id, service_category="technology", **payload.model_dump())
    db.add(row); db.flush(); audit(db, actor, "SERVICE_CREATED", "HospitalityTechnologyService", row.id, f"Created service {row.name}"); db.commit(); db.refresh(row)
    return row


def update_service(db, row, payload, actor):
    for key, value in payload.model_dump(exclude_unset=True).items():
        if key == "owner_user_id" and value: require_user(db, value, row.organization_id)
        if key == "department_id" and value and not db.query(Department).filter_by(id=value, organization_id=row.organization_id).first(): raise HTTPException(422, "Department does not belong to this organization")
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    audit(db, actor, "SERVICE_UPDATED", "HospitalityTechnologyService", row.id, f"Updated service {row.name}"); db.commit(); db.refresh(row)
    return row


def link_service_asset(db, service, asset_id, relationship_type, actor):
    require_asset(db, asset_id, service.organization_id)
    row = db.query(ServiceAssetRelationship).filter_by(service_id=service.id, asset_id=asset_id).first()
    if not row:
        row = ServiceAssetRelationship(organization_id=service.organization_id, service_id=service.id, asset_id=asset_id, relationship_type=relationship_type, created_by=actor.id)
        db.add(row); audit(db, actor, "SERVICE_ASSET_LINKED", "HospitalityTechnologyService", service.id, f"Linked asset {asset_id}"); db.commit()
    return row


def link_service_device(db, service, device_id, actor):
    require_device(db, device_id, service.organization_id)
    row = db.query(DeviceTechnologyService).filter_by(technology_service_id=service.id, device_id=device_id).first()
    if not row:
        row = DeviceTechnologyService(technology_service_id=service.id, device_id=device_id, relationship_type="supports", is_primary=False)
        db.add(row); audit(db, actor, "SERVICE_DEVICE_LINKED", "HospitalityTechnologyService", service.id, f"Linked device {device_id}"); db.commit()
    return row


def service_present(db, row, detail=False):
    assets = db.query(ManagedAsset).join(ServiceAssetRelationship, ServiceAssetRelationship.asset_id == ManagedAsset.id).filter(ServiceAssetRelationship.service_id == row.id).all()
    devices = db.query(Device).join(DeviceTechnologyService, DeviceTechnologyService.device_id == Device.id).filter(DeviceTechnologyService.technology_service_id == row.id).all()
    incidents = db.query(OperationalIncident).filter_by(technology_service_id=row.id).order_by(OperationalIncident.created_at.desc()).all()
    department = db.query(Department).filter_by(id=row.department_id, organization_id=row.organization_id).first() if row.department_id else None
    location = None
    if row.location_id and row.location_type in {"building", "floor", "room"}:
        location = db.query({"building": Building, "floor": Floor, "room": Room}[row.location_type]).filter_by(id=row.location_id, organization_id=row.organization_id).first()
    result = {"id": row.id, "organization_id": row.organization_id, "property_id": row.property_id, "service_id": f"SVC-{str(row.id).split('-')[0].upper()}", "name": row.name, "code": row.code, "description": row.description, "status": row.status, "criticality": row.criticality, "owner_team": row.owner_team, "owner_user_id": row.owner_user_id, "notes": row.notes, "department_id": row.department_id, "department": department.name if department else None, "location_type": row.location_type, "location_id": row.location_id, "location": location.name if location else None, "asset_count": len(assets), "device_count": len(devices), "open_incidents": sum(status_of(x) not in {"resolved", "closed"} for x in incidents), "created_at": row.created_at, "updated_at": row.updated_at}
    if detail: result.update(assets=[{"id": x.id, "asset_number": x.asset_number, "name": x.name, "asset_tag": x.asset_tag} for x in assets], devices=[{"id": x.id, "hostname": x.hostname, "ip_address": x.ip_address} for x in devices], incidents=[{"id": x.id, "incident_number": x.incident_number, "title": x.title, "status": status_of(x), "priority": x.priority} for x in incidents])
    return result


def create_incident(db, payload, actor, organization_id):
    require_property(db, payload.property_id, organization_id)
    source_alert = None
    if payload.alert_id:
        source_alert = db.query(Alert).join(Device, Device.id == Alert.device_id).filter(
            Alert.id == payload.alert_id,
            Device.property_id == payload.property_id,
        ).first()
        if not source_alert:
            raise HTTPException(404, "Alert not found in this property")
    if payload.asset_id: require_asset(db, payload.asset_id, organization_id)
    if payload.device_id: require_device(db, payload.device_id, organization_id)
    if payload.service_id: require_service(db, payload.service_id, organization_id)
    if payload.assigned_technician_id: require_eligible_technician(db, payload.assigned_technician_id, organization_id, payload.property_id)
    values = payload.model_dump(exclude={"service_id", "alert_id"})
    if source_alert and not values.get("device_id"):
        values["device_id"] = source_alert.device_id
    row = OperationalIncident(**values, technology_service_id=payload.service_id, organization_id=organization_id, incident_number=f"INC-{datetime.now(timezone.utc):%Y%m%d}-{secrets.token_hex(3).upper()}", incident_type=payload.category, status="new", source_type="alert" if payload.alert_id else "manual", source_reference_type="alert" if payload.alert_id else None, source_reference_id=payload.alert_id, declared_at=datetime.now(timezone.utc), detected_at=datetime.now(timezone.utc), created_by=actor.username)
    db.add(row); db.flush()
    if payload.asset_id: db.add(IncidentAssetRelationship(organization_id=organization_id, incident_id=row.id, asset_id=payload.asset_id, created_by=actor.id))
    if payload.alert_id: db.add(OperationalIncidentSource(incident_id=row.id, source_type="alert", source_entity_type="alert", source_entity_id=payload.alert_id, relationship_type="triggered", linked_by=actor.username))
    timeline(db, row, actor, "incident_created", "Incident created", row.description)
    audit(db, actor, "INCIDENT_CREATED", "OperationalIncident", row.id, f"Created {row.incident_number}"); db.commit(); db.refresh(row)
    return row


def update_incident(db, row, payload, actor):
    values = payload.model_dump(exclude_unset=True)
    if "service_id" in values:
        service_id = values.pop("service_id")
        if service_id: require_service(db, service_id, row.organization_id)
        row.technology_service_id = service_id
    if "asset_id" in values:
        asset_id = values["asset_id"]
        if asset_id: require_asset(db, asset_id, row.organization_id)
    if values.get("assigned_technician_id"): require_eligible_technician(db, values["assigned_technician_id"], row.organization_id, row.property_id)
    for key, value in values.items(): setattr(row, key, value)
    row.updated_by = actor.username; timeline(db, row, actor, "incident_updated", "Incident details updated")
    audit(db, actor, "INCIDENT_UPDATED", "OperationalIncident", row.id, f"Updated {row.incident_number}"); db.commit(); db.refresh(row); return row


def assign_incident(db, row, technician_id, assigned_team, actor):
    technician = require_eligible_technician(db, technician_id, row.organization_id, row.property_id)
    previous = db.get(User, row.assigned_technician_id) if row.assigned_technician_id else None
    row.assigned_technician_id = technician.id
    if assigned_team is not None:
        row.assigned_team = assigned_team
    row.updated_by = actor.username
    summary = f"Assigned to {technician.username}"
    if previous and previous.id != technician.id:
        summary = f"Reassigned from {previous.username} to {technician.username}"
    timeline(db, row, actor, "incident_assigned", "Ticket assignment changed", summary)
    from app.services.incident_notification_service import notify_incident
    notify_incident(db, row, "assignment", summary)
    audit(db, actor, "INCIDENT_ASSIGNED", "OperationalIncident", row.id, f"{row.incident_number}: {summary}")
    db.commit(); db.refresh(row)
    return row


def transition_incident(db, row, target, payload, actor):
    current = status_of(row)
    if target not in TRANSITIONS.get(current, set()): raise HTTPException(409, f"Invalid incident transition from {current} to {target}")
    now = datetime.now(timezone.utc)
    if target == "resolved":
        if not payload.resolution_summary or len(payload.resolution_summary.strip()) < 3: raise HTTPException(422, "Resolution summary is required")
        row.resolution_summary, row.root_cause_notes, row.follow_up_notes, row.resolved_at = payload.resolution_summary.strip(), payload.root_cause_notes, payload.follow_up_notes, now
    if target == "closed":
        if current != "resolved" or not row.resolution_summary: raise HTTPException(409, "A resolved incident with a resolution summary is required before closure")
        if not payload.closure_notes or len(payload.closure_notes.strip()) < 3: raise HTTPException(422, "Closure notes are required")
        row.closure_notes, row.closed_at = payload.closure_notes.strip(), now
    if target == "acknowledged": row.acknowledged_at = now
    if target == "in_progress" and current in {"resolved", "closed"}: row.resolved_at, row.closed_at = None, None
    row.status, row.updated_by = target, actor.username
    timeline(db, row, actor, "status_changed", f"Status changed to {target.replace('_', ' ')}", payload.reason or payload.resolution_summary or payload.closure_notes)
    audit(db, actor, "INCIDENT_STATUS_CHANGED", "OperationalIncident", row.id, f"{current} to {target}"); db.commit(); db.refresh(row); return row


def add_note(db, row, note, actor):
    entry = timeline(db, row, actor, "note", "Operational note added", note)
    audit(db, actor, "INCIDENT_NOTE_ADDED", "OperationalIncident", row.id, f"Note added to {row.incident_number}"); db.commit(); db.refresh(entry); return entry


def incident_present(db, row, detail=False):
    service = db.get(HospitalityTechnologyService, row.technology_service_id) if row.technology_service_id else None
    asset = db.get(ManagedAsset, row.asset_id) if row.asset_id else None
    device = db.get(Device, row.device_id) if row.device_id else None
    technician = db.get(User, row.assigned_technician_id) if row.assigned_technician_id else None
    department = db.get(Department, row.department_id) if row.department_id else None
    vendor = db.get(Vendor, asset.vendor_id) if asset and asset.vendor_id else None
    contact = db.query(VendorContact).filter_by(vendor_id=vendor.id, primary=True).first() if vendor else None
    procurement = db.query(AssetProcurement).join(ProcurementAssetLink, ProcurementAssetLink.procurement_id == AssetProcurement.id).filter(ProcurementAssetLink.asset_id == asset.id).first() if asset else None
    impact = db.query(IncidentImpactAssessment).filter_by(incident_id=row.id).order_by(IncidentImpactAssessment.assessed_at.desc()).first()
    result = {"id": row.id, "incident_number": row.incident_number, "title": row.title, "description": row.description, "status": status_of(row), "priority": row.priority, "severity": row.severity, "category": row.category or row.incident_type, "source": row.source_type or "manual", "source_alert_id": row.source_reference_id if row.source_reference_type == "alert" else None, "assigned_team": row.assigned_team, "assigned_technician_id": row.assigned_technician_id, "assigned_technician": technician.username if technician else None, "requester_id": row.requester_id, "asset_id": row.asset_id, "device_id": row.device_id, "service_id": row.technology_service_id, "service_name": service.name if service else None, "department": department.name if department else None, "location": None, "created_at": row.created_at, "acknowledged_at": row.acknowledged_at, "resolved_at": row.resolved_at, "closed_at": row.closed_at, "resolution_summary": row.resolution_summary, "root_cause_notes": row.root_cause_notes, "follow_up_notes": row.follow_up_notes, "closure_notes": row.closure_notes, "time_to_acknowledge_seconds": int((row.acknowledged_at-row.created_at).total_seconds()) if row.acknowledged_at else None, "time_to_resolve_seconds": int((row.resolved_at-row.created_at).total_seconds()) if row.resolved_at else None, "asset": {"id": asset.id, "asset_number": asset.asset_number, "asset_tag": asset.asset_tag, "name": asset.name} if asset else None, "device": {"id": device.id, "hostname": device.hostname, "ip_address": device.ip_address} if device else None, "vendor": {"id": vendor.id, "name": vendor.legal_name, "support_contact": contact.name if contact else None} if vendor else None, "procurement": {"id": procurement.id, "procurement_number": procurement.procurement_number, "title": procurement.title} if procurement else None, "impact": {"confirmed_affected": 0, "potentially_affected": 0, "confidence_score": impact.confidence_score} if impact else None}
    if detail:
        events = db.query(IncidentTimelineEntry).filter_by(incident_id=row.id).order_by(IncidentTimelineEntry.occurred_at).all()
        result["timeline"] = [{"id": x.id, "type": x.entry_type, "title": x.title, "summary": x.summary, "author": x.actor_user_id, "timestamp": x.occurred_at} for x in events]
    return result
