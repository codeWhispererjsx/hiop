from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.security import require_roles
from app.models.user import User
from app.schemas.report import ReportPage, ReportsSummary
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["Reports"])
admin = require_roles(["admin"])


@router.get("/summary", response_model=ReportsSummary)
def summary(start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db), _: User = Depends(admin)):
    return report_service.summary(db, start_date, end_date)


@router.get("/{report_name}/export")
def export_report(
    report_name: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    search: str | None = Query(None, max_length=200),
    status: str | None = None,
    department: str | None = None,
    category: str | None = None,
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(admin),
):
    content, filename = report_service.export_csv(db, report_name, start_date, end_date, search, status, department, category, sort_by, sort_order)
    return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/{report_name}", response_model=ReportPage)
def report(
    report_name: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    search: str | None = Query(None, max_length=200),
    status: str | None = None,
    department: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: str | None = None,
    sort_order: str = Query("asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _: User = Depends(admin),
):
    return report_service.get_report(db, report_name, start_date, end_date, search, status, department, category, page, page_size, sort_by, sort_order)
