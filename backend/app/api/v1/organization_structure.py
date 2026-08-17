from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import allowed_property_ids, organization_context
from app.models.asset_intelligence import ManagedAsset
from app.models.device import Device
from app.models.hierarchy import Building, Department, Floor, Organization, Property, Room
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.local_agent import LocalAgentRegistration
from app.models.user import User
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/organization-structure", tags=["Organization Structure"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
manager = require_roles(["admin"])


class OrganizationPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=160)
    code: str | None = Field(None, min_length=2, max_length=40)
    contact_email: str | None = Field(None, max_length=255)
    contact_phone: str | None = Field(None, max_length=40)
    timezone: str | None = Field(None, max_length=64)
    address: str | None = Field(None, max_length=500)
    description: str | None = Field(None, max_length=4000)


class DepartmentWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(None, max_length=40)
    description: str | None = Field(None, max_length=500)


class LocationWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(None, max_length=40)
    type: Literal["building", "floor", "room", "area", "server_room", "other"]
    parent_id: UUID | None = None
    description: str | None = Field(None, max_length=255)


class AssignmentWrite(BaseModel):
    department_id: UUID | None = None
    location_type: Literal["building", "floor", "room"] | None = None
    location_id: UUID | None = None


class AgentWrite(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    version: str | None = Field(None, max_length=50)


def _audit(db, actor, action, entity_type, entity_id, detail, organization_id):
    create_audit_log(db, actor.username, action, entity_type, str(entity_id), f"Organization {organization_id}: {detail}")


def _organization(db, organization_id):
    row = db.get(Organization, organization_id)
    if not row: raise HTTPException(404, "Organization not found")
    return row


def _department(db, department_id, organization_id):
    if department_id is None: return None
    row = db.query(Department).filter_by(id=department_id, organization_id=organization_id).first()
    if not row: raise HTTPException(422, "Department does not belong to this organization")
    return row


LOCATION_MODELS = {"building": Building, "floor": Floor, "room": Room}
def _location(db, kind, row_id, organization_id):
    if kind is None and row_id is None: return None
    if not kind or not row_id or kind not in LOCATION_MODELS: raise HTTPException(422, "A valid location type and ID are required together")
    row = db.query(LOCATION_MODELS[kind]).filter_by(id=row_id, organization_id=organization_id).first()
    if not row: raise HTTPException(422, "Location does not belong to this organization")
    return row


def _org_view(row):
    return {key: getattr(row, key) for key in ("id", "name", "code", "status", "contact_email", "contact_phone", "timezone", "address", "description", "updated_at")}


@router.get("/organization")
def get_organization(db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    return _org_view(_organization(db, organization_id))


@router.patch("/organization")
def update_organization(payload: OrganizationPatch, db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    row = _organization(db, organization_id)
    for key, value in payload.model_dump(exclude_unset=True).items(): setattr(row, key, value.strip() if isinstance(value, str) else value)
    _audit(db, actor, "ORGANIZATION_UPDATED", "Organization", row.id, "Updated organization information", organization_id)
    db.commit(); db.refresh(row)
    return _org_view(row)


def _department_view(row):
    return {"id": row.id, "name": row.name, "code": row.code, "description": row.description, "status": row.status, "is_active": row.is_active, "created_at": row.created_at, "updated_at": row.updated_at}


@router.get("/departments")
def list_departments(db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    return [_department_view(x) for x in db.query(Department).filter_by(organization_id=organization_id).order_by(Department.name).all()]


@router.post("/departments", status_code=201)
def create_department(payload: DepartmentWrite, db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    if db.query(Department).filter(Department.organization_id == organization_id, func.lower(Department.name) == payload.name.strip().lower()).first(): raise HTTPException(409, "Department already exists")
    row = Department(organization_id=organization_id, name=payload.name.strip(), code=payload.code, description=payload.description, status="active", is_active=True)
    db.add(row); db.flush(); _audit(db, actor, "DEPARTMENT_CREATED", "Department", row.id, f"Created {row.name}", organization_id)
    try: db.commit(); db.refresh(row)
    except IntegrityError as exc: db.rollback(); raise HTTPException(409, "Department code or name already exists") from exc
    return _department_view(row)


@router.patch("/departments/{department_id}")
def update_department(department_id: UUID, payload: DepartmentWrite, db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    row = _department(db, department_id, organization_id)
    row.name, row.code, row.description = payload.name.strip(), payload.code, payload.description
    _audit(db, actor, "DEPARTMENT_UPDATED", "Department", row.id, f"Updated {row.name}", organization_id); db.commit(); db.refresh(row)
    return _department_view(row)


@router.post("/departments/{department_id}/{action}")
def set_department_status(department_id: UUID, action: Literal["activate", "deactivate"], db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    row = _department(db, department_id, organization_id); row.is_active = action == "activate"; row.status = "active" if row.is_active else "inactive"
    _audit(db, actor, f"DEPARTMENT_{action.upper()}D", "Department", row.id, f"{action.title()}d {row.name}", organization_id); db.commit(); db.refresh(row)
    return _department_view(row)


def _location_view(kind, row, parent_id=None):
    return {"id": row.id, "name": row.name, "code": getattr(row, "code", None), "type": getattr(row, "type", kind) if kind == "room" else kind, "kind": kind, "parent_id": parent_id, "description": getattr(row, "description", None), "status": getattr(row, "status", "active"), "is_active": row.is_active}


@router.get("/locations")
def list_locations(db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    values=[]
    values += [_location_view("building", x) for x in db.query(Building).filter_by(organization_id=organization_id).all()]
    values += [_location_view("floor", x, x.building_id) for x in db.query(Floor).filter_by(organization_id=organization_id).all()]
    values += [_location_view("room", x, x.floor_id) for x in db.query(Room).filter_by(organization_id=organization_id).all()]
    return sorted(values, key=lambda x: (x["type"], x["name"].lower()))


@router.post("/locations", status_code=201)
def create_location(payload: LocationWrite, db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    kind = "room" if payload.type in {"room", "area", "server_room", "other"} else payload.type
    model = LOCATION_MODELS[kind]
    if db.query(model).filter(model.organization_id == organization_id, func.lower(model.name) == payload.name.strip().lower()).first(): raise HTTPException(409, "Location already exists")
    values={"organization_id": organization_id, "name": payload.name.strip(), "is_active": True, "description": payload.description, "status": "active"}
    if kind == "building":
        prop=db.query(Property).filter_by(organization_id=organization_id).first(); values.update(property_id=prop.id if prop else None, code=payload.code)
    elif kind == "floor":
        parent=_location(db, "building", payload.parent_id, organization_id); values.update(building_id=parent.id)
    else:
        parent=_location(db, "floor", payload.parent_id, organization_id); values.update(floor_id=parent.id, code=payload.code, type=payload.type)
    row=model(**values); db.add(row); db.flush(); _audit(db, actor, "LOCATION_CREATED", model.__name__, row.id, f"Created {payload.type} {row.name}", organization_id); db.commit(); db.refresh(row)
    return _location_view(kind, row, getattr(row, "building_id", getattr(row, "floor_id", None)))


@router.patch("/locations/{kind}/{location_id}")
def update_location(kind: Literal["building", "floor", "room"], location_id: UUID, payload: LocationWrite, db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    row=_location(db, kind, location_id, organization_id)
    row.name=payload.name.strip(); row.description=payload.description
    if hasattr(row, "code"): row.code=payload.code
    if kind == "floor": row.building_id=_location(db, "building", payload.parent_id, organization_id).id
    elif kind == "room":
        row.floor_id=_location(db, "floor", payload.parent_id, organization_id).id
        row.type=payload.type
    _audit(db, actor, "LOCATION_UPDATED", row.__class__.__name__, row.id, f"Updated {row.name}", organization_id); db.commit(); db.refresh(row)
    return _location_view(kind, row, getattr(row, "building_id", getattr(row, "floor_id", None)))


@router.post("/locations/{kind}/{location_id}/{action}")
def set_location_status(kind: Literal["building", "floor", "room"], location_id: UUID, action: Literal["activate", "deactivate"], db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    row=_location(db, kind, location_id, organization_id); row.is_active=action == "activate"; row.status="active" if row.is_active else "inactive"
    _audit(db, actor, f"LOCATION_{action.upper()}D", row.__class__.__name__, row.id, f"{action.title()}d {row.name}", organization_id); db.commit()
    return _location_view(kind, row, getattr(row, "building_id", getattr(row, "floor_id", None)))


@router.patch("/assignments/{entity_type}/{entity_id}")
def assign(entity_type: Literal["asset", "user", "service"], entity_id: str, payload: AssignmentWrite, db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    department=_department(db, payload.department_id, organization_id); location=_location(db, payload.location_type, payload.location_id, organization_id)
    if entity_type == "asset":
        row=db.query(ManagedAsset).filter_by(id=entity_id, organization_id=organization_id).first()
        if not row: raise HTTPException(404, "Asset not found")
        row.department_id=department.id if department else None; row.department_name=department.name if department else None
        row.room_id=location.id if payload.location_type == "room" and location else None; row.location_name=location.name if location else None
        row.field_sources={**(row.field_sources or {}), "department":{"source":"manual","status":"confirmed"}, "location":{"source":"manual","status":"confirmed"}}
    elif entity_type == "user":
        row=db.query(User).filter_by(id=entity_id, organization_id=organization_id).first()
        if not row: raise HTTPException(404, "User not found")
        row.department_id=department.id if department else None; row.primary_location_type=payload.location_type; row.primary_location_id=location.id if location else None
    else:
        row=db.query(HospitalityTechnologyService).filter_by(id=entity_id, organization_id=organization_id).first()
        if not row: raise HTTPException(404, "Service not found")
        row.department_id=department.id if department else None; row.location_type=payload.location_type; row.location_id=location.id if location else None
    _audit(db, actor, "ORGANIZATION_ASSIGNMENT_UPDATED", entity_type.title(), entity_id, "Updated confirmed department/location assignment", organization_id); db.commit()
    return {"ok": True, "department": department.name if department else None, "location": location.name if location else None, "source": "manual", "status": "confirmed"}


@router.get("/department-suggestion/{asset_id}")
def suggest_department(asset_id: UUID, db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    asset=db.query(ManagedAsset).filter_by(id=asset_id, organization_id=organization_id).first()
    if not asset: raise HTTPException(404, "Asset not found")
    if asset.department_id: return {"department_id": asset.department_id, "department": asset.department_name, "status":"confirmed", "source":"manual"}
    device=db.get(Device, asset.device_id) if asset.device_id else None
    ad_text=" ".join(filter(None, [getattr(device, "ad_organizational_unit", None), getattr(device, "ad_distinguished_name", None)])).lower() if device else ""
    hostname_text=" ".join(filter(None, [asset.name, getattr(device, "hostname", None)])).lower()
    for department in db.query(Department).filter_by(organization_id=organization_id, is_active=True).all():
        tokens=[x.lower() for x in (department.code, department.name) if x and len(x) >= 2]
        if any(token in ad_text for token in tokens): return {"department_id":department.id, "department":department.name, "status":"suggested", "source":"active_directory_ou"}
        if any(token in hostname_text for token in tokens): return {"department_id":department.id, "department":department.name, "status":"suggested", "source":"hostname_rule"}
    return {"department_id":None, "department":None, "status":"unknown", "source":None}


@router.get("/agents")
def list_agents(db: Session = Depends(get_db), _=Depends(reader), organization_id=Depends(organization_context)):
    allowed=allowed_property_ids(db, _, organization_id)
    return db.query(LocalAgentRegistration).filter(LocalAgentRegistration.organization_id==organization_id,LocalAgentRegistration.property_id.in_(allowed)).order_by(LocalAgentRegistration.name).all()


@router.post("/agents", status_code=201)
def register_agent(payload: AgentWrite, db: Session = Depends(get_db), actor=Depends(manager), organization_id=Depends(organization_context)):
    raise HTTPException(410, "Direct agent registration was replaced by one-time enrollment")


@router.post("/agents/{agent_id}/heartbeat")
def heartbeat(agent_id: UUID, db: Session = Depends(get_db), _=Depends(manager), organization_id=Depends(organization_context)):
    raise HTTPException(410, "Human-authenticated heartbeat was replaced by machine authentication")
