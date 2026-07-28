from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.hierarchy import Organization, Property
from app.schemas.hospitality import OrganizationRead, OrganizationWrite, PropertyRead, PropertyWrite
from app.services.audit_service import create_audit_log
from app.services.hospitality_service import HospitalityService

router = APIRouter(tags=["Hospitality foundation"])
reader = require_roles(["admin", "technician"])
admin = require_roles(["admin"])


def page(query, page: int, page_size: int):
    total = query.count()
    return {"items": query.offset((page - 1) * page_size).limit(page_size).all(), "total": total, "page": page, "page_size": page_size}


@router.get("/organizations")
def organizations(search: str | None = None, status_filter: str | None = Query(None, alias="status"), page_number: int = Query(1, alias="page", ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    query = db.query(Organization).order_by(Organization.name)
    if search: query = query.filter(Organization.name.ilike(f"%{search.strip()}%"))
    if status_filter: query = query.filter(Organization.status == status_filter)
    return page(query, page_number, page_size)


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(payload: OrganizationWrite, db: Session = Depends(get_db), user=Depends(admin)):
    service = HospitalityService(db); service.ensure_unique(Organization, payload.name, payload.code)
    row = Organization(**payload.model_dump()); db.add(row); db.flush()
    create_audit_log(db, user.username, "CREATE_ORGANIZATION", "Organization", str(row.id), f"Created organization {row.name}")
    db.commit(); db.refresh(row); return row


@router.get("/properties")
def properties(search: str | None = None, organization_id: UUID | None = None, status_filter: str | None = Query(None, alias="status"), property_type: str | None = Query(None, alias="type"), page_number: int = Query(1, alias="page", ge=1), page_size: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), _=Depends(reader)):
    query = db.query(Property).order_by(Property.name)
    if search: query = query.filter(Property.name.ilike(f"%{search.strip()}%"))
    if organization_id: query = query.filter(Property.organization_id == organization_id)
    if status_filter: query = query.filter(Property.operational_status == status_filter)
    if property_type: query = query.filter(Property.type == property_type)
    return page(query, page_number, page_size)


@router.post("/properties", response_model=PropertyRead, status_code=status.HTTP_201_CREATED)
def create_property(payload: PropertyWrite, db: Session = Depends(get_db), user=Depends(admin)):
    service = HospitalityService(db)
    if payload.organization_id: service.organization(payload.organization_id)
    service.ensure_unique(Property, payload.name, payload.code)
    row = Property(**payload.model_dump()); db.add(row); db.flush()
    create_audit_log(db, user.username, "CREATE_PROPERTY", "Property", str(row.id), f"Created property {row.name}")
    db.commit(); db.refresh(row); return row


@router.get("/properties/{property_id}", response_model=PropertyRead)
def property_detail(property_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return HospitalityService(db).property(property_id)


@router.patch("/properties/{property_id}", response_model=PropertyRead)
def update_property(property_id: UUID, payload: PropertyWrite, db: Session = Depends(get_db), user=Depends(admin)):
    service = HospitalityService(db); row = service.property(property_id)
    if payload.organization_id: service.organization(payload.organization_id)
    service.ensure_unique(Property, payload.name, payload.code, property_id)
    for key, value in payload.model_dump().items(): setattr(row, key, value)
    create_audit_log(db, user.username, "UPDATE_PROPERTY", "Property", str(row.id), f"Updated property {row.name}")
    db.commit(); db.refresh(row); return row


@router.delete("/properties/{property_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_property(property_id: UUID, db: Session = Depends(get_db), user=Depends(admin)):
    row = HospitalityService(db).property(property_id); row.operational_status = "archived"; row.is_active = False
    create_audit_log(db, user.username, "ARCHIVE_PROPERTY", "Property", str(row.id), f"Archived property {row.name}")
    db.commit()
