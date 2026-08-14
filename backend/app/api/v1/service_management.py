from datetime import date, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.models.asset_intelligence import ManagedAsset
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.incidents import OperationalIncident
from app.models.service_management import IncidentAssetRelationship, ServiceAssetRelationship
from app.schemas.service_management import IncidentPatch, NoteWrite, OperationalIncidentWrite, RelationshipWrite, ServicePatch, ServiceWrite, TransitionWrite
from app.services import service_management_service as service

router = APIRouter(prefix="/service-management", tags=["Service Management"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
operator = require_roles(["admin", "technician"])
admin = require_roles(["admin"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    incidents = db.query(OperationalIncident).filter_by(organization_id=organization_id).all()
    statuses = [service.status_of(row) for row in incidents]
    today = datetime.now(timezone.utc).date()
    resolved_today = sum(bool(row.resolved_at and row.resolved_at.date() == today) for row in incidents)
    durations = [(row.resolved_at-row.created_at).total_seconds() for row in incidents if row.resolved_at]
    services = db.query(HospitalityTechnologyService).filter_by(organization_id=organization_id).all()
    return {"total": len(incidents), "open": sum(x not in {"resolved", "closed"} for x in statuses), "critical": sum(row.priority == "critical" or row.severity == "critical" for row in incidents if service.status_of(row) not in {"resolved", "closed"}), "unassigned": sum(not row.assigned_technician_id for row in incidents if service.status_of(row) not in {"resolved", "closed"}), "in_progress": statuses.count("in_progress"), "on_hold": statuses.count("on_hold"), "resolved_today": resolved_today, "average_resolution_seconds": int(sum(durations)/len(durations)) if durations else None, "services": len(services), "services_operational": sum(x.status == "operational" for x in services), "services_degraded": sum(x.status == "degraded" for x in services), "services_outage": sum(x.status == "outage" for x in services)}


@router.get("/services")
def list_services(search: str | None = None, status: str | None = None, criticality: str | None = None, db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    query = db.query(HospitalityTechnologyService).filter_by(organization_id=organization_id)
    if search: query = query.filter(or_(HospitalityTechnologyService.name.ilike(f"%{search}%"), HospitalityTechnologyService.code.ilike(f"%{search}%")))
    if status: query = query.filter_by(status=status)
    if criticality: query = query.filter_by(criticality=criticality)
    return [service.service_present(db, row) for row in query.order_by(HospitalityTechnologyService.name).all()]


@router.post("/services", status_code=201)
def create_service(payload: ServiceWrite, db: Session = Depends(get_db), actor=Depends(admin), organization_id=Depends(organization_context)):
    return service.service_present(db, service.create_service(db, payload, actor, organization_id), True)


@router.get("/services/{service_id}")
def get_service(service_id: UUID, db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    return service.service_present(db, service.require_service(db, service_id, organization_id), True)


@router.patch("/services/{service_id}")
def update_service(service_id: UUID, payload: ServicePatch, db: Session = Depends(get_db), actor=Depends(admin), organization_id=Depends(organization_context)):
    row = service.require_service(db, service_id, organization_id)
    return service.service_present(db, service.update_service(db, row, payload, actor), True)


@router.post("/services/{service_id}/assets", status_code=201)
def link_service_asset(service_id: UUID, payload: RelationshipWrite, db: Session = Depends(get_db), actor=Depends(admin), organization_id=Depends(organization_context)):
    row = service.require_service(db, service_id, organization_id); service.link_service_asset(db, row, payload.asset_id, payload.relationship_type, actor)
    return service.service_present(db, row, True)


@router.post("/services/{service_id}/devices/{device_id}", status_code=201)
def link_service_device(service_id: UUID, device_id: UUID, db: Session = Depends(get_db), actor=Depends(admin), organization_id=Depends(organization_context)):
    row = service.require_service(db, service_id, organization_id); service.link_service_device(db, row, device_id, actor)
    return service.service_present(db, row, True)


@router.get("/incidents")
def list_incidents(search: str | None = None, status: str | None = None, priority: str | None = None, severity: str | None = None, category: str | None = None, technician_id: str | None = None, service_id: UUID | None = None, asset_id: UUID | None = None, date_from: date | None = None, db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    query = db.query(OperationalIncident).filter_by(organization_id=organization_id)
    if search:
        query = query.outerjoin(ManagedAsset, ManagedAsset.id == OperationalIncident.asset_id).filter(or_(OperationalIncident.incident_number.ilike(f"%{search}%"), OperationalIncident.title.ilike(f"%{search}%"), OperationalIncident.description.ilike(f"%{search}%"), ManagedAsset.asset_number.ilike(f"%{search}%"), ManagedAsset.asset_tag.ilike(f"%{search}%")))
    if priority: query = query.filter_by(priority=priority)
    if severity: query = query.filter_by(severity=severity)
    if category: query = query.filter_by(category=category)
    if technician_id: query = query.filter_by(assigned_technician_id=technician_id)
    if service_id: query = query.filter_by(technology_service_id=service_id)
    if asset_id: query = query.filter(or_(OperationalIncident.asset_id == asset_id, OperationalIncident.id.in_(db.query(IncidentAssetRelationship.incident_id).filter_by(asset_id=asset_id))))
    if date_from: query = query.filter(OperationalIncident.created_at >= date_from)
    rows = query.order_by(OperationalIncident.created_at.desc()).all()
    values = [service.incident_present(db, row) for row in rows]
    return [row for row in values if not status or row["status"] == status]


@router.post("/incidents", status_code=201)
def create_incident(payload: OperationalIncidentWrite, db: Session = Depends(get_db), actor=Depends(operator), organization_id=Depends(organization_context)):
    return service.incident_present(db, service.create_incident(db, payload, actor, organization_id), True)


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: UUID, db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    return service.incident_present(db, service.require_incident(db, incident_id, organization_id), True)


@router.patch("/incidents/{incident_id}")
def update_incident(incident_id: UUID, payload: IncidentPatch, db: Session = Depends(get_db), actor=Depends(operator), organization_id=Depends(organization_context)):
    row = service.require_incident(db, incident_id, organization_id)
    if actor.role == "technician" and row.assigned_technician_id not in {None, actor.id}: raise HTTPException(403, "Technicians may update only unassigned incidents or incidents assigned to them")
    return service.incident_present(db, service.update_incident(db, row, payload, actor), True)


@router.post("/incidents/{incident_id}/transition/{target}")
def transition_incident(incident_id: UUID, target: str, payload: TransitionWrite, db: Session = Depends(get_db), actor=Depends(operator), organization_id=Depends(organization_context)):
    row = service.require_incident(db, incident_id, organization_id)
    if target == "closed" and actor.role != "admin": raise HTTPException(403, "Only an administrator may close incidents")
    if actor.role == "technician" and row.assigned_technician_id not in {None, actor.id}: raise HTTPException(403, "Incident is assigned to another technician")
    return service.incident_present(db, service.transition_incident(db, row, target, payload, actor), True)


@router.post("/incidents/{incident_id}/notes", status_code=201)
def add_note(incident_id: UUID, payload: NoteWrite, db: Session = Depends(get_db), actor=Depends(operator), organization_id=Depends(organization_context)):
    row = service.require_incident(db, incident_id, organization_id)
    if actor.role == "technician" and row.assigned_technician_id not in {None, actor.id}: raise HTTPException(403, "Incident is assigned to another technician")
    entry = service.add_note(db, row, payload.note, actor)
    return {"id": entry.id, "type": entry.entry_type, "title": entry.title, "summary": entry.summary, "author": entry.actor_user_id, "timestamp": entry.occurred_at}


@router.get("/assets/{asset_id}/incidents")
def asset_incidents(asset_id: UUID, db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    service.require_asset(db, asset_id, organization_id)
    rows = db.query(OperationalIncident).filter(OperationalIncident.organization_id == organization_id, or_(OperationalIncident.asset_id == asset_id, OperationalIncident.id.in_(db.query(IncidentAssetRelationship.incident_id).filter_by(asset_id=asset_id)))).order_by(OperationalIncident.created_at.desc()).all()
    return [service.incident_present(db, row) for row in rows]
