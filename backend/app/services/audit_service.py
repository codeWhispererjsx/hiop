import csv
import io
import math
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Query, Session

from app.models.audit_log import AuditLog


def create_audit_log(
    db: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    description: str
) -> AuditLog:
    audit_log = AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        description=description
    )

    db.add(audit_log)

    return audit_log


SECURITY_ACTIONS = ("USER_PASSWORD_RESET", "USER_ACTIVATED", "USER_DEACTIVATED", "USER_ROLE_CHANGED", "LOGIN_SUCCESS", "LOGIN_FAILED")


def _filtered_query(
    db: Session,
    actor: str | None,
    action: str | None,
    entity_type: str | None,
    entity_id: str | None,
    start_date: datetime | None,
    end_date: datetime | None,
    search: str | None,
) -> Query:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "Start date must be before or equal to end date")
    query = db.query(AuditLog)
    if actor:
        query = query.filter(AuditLog.actor == actor)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.filter(AuditLog.entity_id == entity_id)
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)
    if search and search.strip():
        term = f"%{search.strip()}%"
        query = query.filter(or_(AuditLog.actor.ilike(term), AuditLog.action.ilike(term), AuditLog.entity_type.ilike(term), AuditLog.entity_id.ilike(term), AuditLog.description.ilike(term)))
    return query


def _summary(db: Session) -> dict[str, int]:
    today = datetime.now(timezone.utc).date()
    base = db.query(AuditLog)
    return {
        "total": base.count(),
        "today": base.filter(func.date(AuditLog.created_at) == today).count(),
        "user_actions": base.filter(func.lower(AuditLog.entity_type) == "user").count(),
        "device_actions": base.filter(func.lower(AuditLog.entity_type) == "device").count(),
        "ticket_actions": base.filter(func.lower(AuditLog.entity_type) == "ticket").count(),
        "security_events": base.filter(AuditLog.action.in_(SECURITY_ACTIONS)).count(),
    }


def _options(db: Session) -> dict[str, list[str]]:
    def values(column):
        return [value for value, in db.query(column).filter(column.isnot(None), column != "").distinct().order_by(column).all()]
    return {"actors": values(AuditLog.actor), "actions": values(AuditLog.action), "entity_types": values(AuditLog.entity_type)}


def list_logs(db: Session, actor=None, action=None, entity_type=None, entity_id=None, start_date=None, end_date=None, search=None, page=1, page_size=25, sort_order="desc"):
    query = _filtered_query(db, actor, action, entity_type, entity_id, start_date, end_date, search)
    total = query.count()
    pages = max(1, math.ceil(total / page_size))
    if total and page > pages:
        raise HTTPException(400, "Requested page is outside the filtered result set")
    order = AuditLog.created_at.asc() if sort_order == "asc" else AuditLog.created_at.desc()
    items = query.order_by(order, AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size, "pages": pages, "summary": _summary(db), "options": _options(db)}


def get_log(db: Session, audit_id: str) -> AuditLog:
    log = db.query(AuditLog).filter(AuditLog.id == audit_id).first()
    if not log:
        raise HTTPException(404, "Audit record not found")
    return log


def export_csv(db: Session, actor=None, action=None, entity_type=None, entity_id=None, start_date=None, end_date=None, search=None, sort_order="desc"):
    query = _filtered_query(db, actor, action, entity_type, entity_id, start_date, end_date, search)
    order = AuditLog.created_at.asc() if sort_order == "asc" else AuditLog.created_at.desc()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    generated_at = datetime.now(timezone.utc)
    writer.writerow(["HIOP Audit Export", generated_at.isoformat()])
    writer.writerow(["ID", "Timestamp", "Actor", "Action", "Entity Type", "Entity ID", "Description"])
    for log in query.order_by(order, AuditLog.id.desc()).all():
        writer.writerow([str(log.id), log.created_at.isoformat(), log.actor or "System", log.action, log.entity_type, log.entity_id, log.description])
    filename = f"hiop-audit-{generated_at.strftime('%Y%m%d-%H%M%S')}.csv"
    return "\ufeff" + output.getvalue(), filename
