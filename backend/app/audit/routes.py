from datetime import datetime
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.core.tenant import organization_context, property_context
from app.models.hierarchy import Property
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["Audit"])
admin = require_roles(["admin", "platformadmin"])

def filters(actor: str | None = None, action: str | None = None, entity_type: str | None = None,
            entity_id: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None,
            search: str | None = None, sort_order: Literal["asc", "desc"] = "desc",
            property_id: UUID | None = None, outcome: Literal["success", "failure"] | None = None):
    return dict(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id,
                start_date=start_date, end_date=end_date, search=search, sort_order=sort_order,
                property_id=property_id, outcome=outcome)

def effective_property(db, requested_property_id, scoped_property_id, organization_id):
    if scoped_property_id is not None:
        if requested_property_id is not None and requested_property_id != scoped_property_id:
            raise HTTPException(403, "Property is outside your selected scope")
        return scoped_property_id
    if requested_property_id is not None and not db.query(Property.id).filter(
        Property.id == requested_property_id, Property.organization_id == organization_id
    ).first():
        raise HTTPException(403, "Property is outside your organization")
    return requested_property_id

@router.get("/export")
def export(params=Depends(filters), db: Session=Depends(get_db), user=Depends(admin),
           organization_id=Depends(organization_context), property_id=Depends(property_context)):
    requested_property = params.pop("property_id")
    selected_property = effective_property(db, requested_property, property_id, organization_id)
    content, filename = audit_service.export_csv(db, **params, organization_id=organization_id, property_id=selected_property)
    return Response(content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})

@router.get("")
def logs(params=Depends(filters), page:int=Query(1,ge=1), page_size:int=Query(25,ge=1,le=100),
         db:Session=Depends(get_db), user=Depends(admin), organization_id=Depends(organization_context), property_id=Depends(property_context)):
    requested_property = params.pop("property_id")
    selected_property = effective_property(db, requested_property, property_id, organization_id)
    return audit_service.list_logs(db, **params, page=page, page_size=page_size, organization_id=organization_id, property_id=selected_property)
