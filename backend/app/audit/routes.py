from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
from app.core.security import get_db, require_roles
from app.core.tenant import organization_context, property_context
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["Audit"])
admin = require_roles(["admin", "platformadmin"])

def filters(actor: str | None = None, action: str | None = None, entity_type: str | None = None,
            entity_id: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None,
            search: str | None = None, sort_order: Literal["asc", "desc"] = "desc"):
    return dict(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id,
                start_date=start_date, end_date=end_date, search=search, sort_order=sort_order)

@router.get("/export")
def export(params=Depends(filters), db: Session=Depends(get_db), user=Depends(admin),
           organization_id=Depends(organization_context), property_id=Depends(property_context)):
    content, filename = audit_service.export_csv(db, **params, organization_id=organization_id, property_id=property_id)
    return Response(content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"})

@router.get("")
def logs(params=Depends(filters), page:int=Query(1,ge=1), page_size:int=Query(25,ge=1,le=100),
         db:Session=Depends(get_db), user=Depends(admin), organization_id=Depends(organization_context), property_id=Depends(property_context)):
    return audit_service.list_logs(db, **params, page=page, page_size=page_size, organization_id=organization_id, property_id=property_id)
