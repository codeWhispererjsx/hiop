from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import require_roles
from app.models.user import User
from app.schemas.audit import AuditLogPage, AuditLogResponse
from app.services import audit_service

router = APIRouter(prefix="/audit-logs", tags=["Audit"])
admin = require_roles(["admin"])


@router.get("/export")
def export_audit_logs(
    actor: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    search: str | None = None,
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(admin),
):
    content, filename = audit_service.export_csv(db, actor, action, entity_type, entity_id, start_date, end_date, search, sort_order)
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("", response_model=AuditLogPage)
@router.get("/", response_model=AuditLogPage, include_in_schema=False)
def list_audit_logs(
    actor: str | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(admin),
):
    return audit_service.list_logs(db, actor, action, entity_type, entity_id, start_date, end_date, search, page, page_size, sort_order)


@router.get("/{audit_id}", response_model=AuditLogResponse)
def get_audit_log(audit_id: str, db: Session = Depends(get_db), _: User = Depends(admin)):
    return audit_service.get_log(db, audit_id)
