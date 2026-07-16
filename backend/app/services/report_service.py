import csv
import io
import math
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.network_scan import NetworkScan
from app.models.ticket import Ticket
from app.models.user import User

REPORTS = {
    "devices": ("Device Inventory Report", Device, Device.created_at),
    "network": ("Network Status Report", NetworkScan, NetworkScan.scanned_at),
    "alerts": ("Alerts Report", Alert, Alert.created_at),
    "tickets": ("Tickets Report", Ticket, Ticket.created_at),
    "users": ("Users Report", User, User.created_at),
    "audit": ("Audit Report", AuditLog, AuditLog.created_at),
}


def _csv_safe(value):
    text_value = str(value) if value is not None else ""
    return f"'{text_value}" if text_value.startswith(("=", "+", "-", "@")) else text_value


def _validate(report_name: str, start_date: datetime | None, end_date: datetime | None):
    if report_name not in REPORTS:
        raise HTTPException(404, "Report not found")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "Start date must be before or equal to end date")


def _date(query, column, start_date, end_date):
    if start_date:
        query = query.filter(column >= start_date)
    if end_date:
        query = query.filter(column <= end_date)
    return query


def _value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None and value.__class__.__name__ == "UUID" else value


def _page(items: list[dict[str, Any]], page: int, page_size: int):
    total = len(items)
    pages = max(1, math.ceil(total / page_size))
    if total and page > pages:
        raise HTTPException(400, "Requested page is outside the report result set")
    return items[(page - 1) * page_size:page * page_size], total, pages


def _distribution(values, key="name"):
    counts: dict[str, int] = {}
    for value in values:
        label = str(value or "Unassigned")
        counts[label] = counts.get(label, 0) + 1
    return [{key: label, "value": count} for label, count in sorted(counts.items())]


def summary(db: Session, start_date=None, end_date=None):
    _validate("devices", start_date, end_date)
    now = datetime.now(timezone.utc)
    cards = []
    for key, (title, model, column) in REPORTS.items():
        count = _date(db.query(model), column, start_date, end_date).count()
        cards.append({"key": key, "title": title, "total_records": count, "last_generated": now, "export_formats": ["csv"]})
    return {"generated_at": now, "cards": cards}


def _device_rows(db, start_date, end_date, search):
    query = _date(db.query(Device), Device.created_at, start_date, end_date)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Device.asset_tag.ilike(term), Device.hostname.ilike(term), Device.device_type.ilike(term), Device.department.ilike(term), Device.location.ilike(term), Device.ip_address.ilike(term)))
    devices = query.all()
    scan_query = _date(db.query(NetworkScan), NetworkScan.scanned_at, start_date, end_date)
    scans = scan_query.order_by(NetworkScan.scanned_at.desc()).all()
    latest = {}
    for scan in scans:
        latest.setdefault(str(scan.device_id), scan)
    rows = []
    for device in devices:
        scan = latest.get(str(device.id))
        rows.append({"id": str(device.id), "asset_tag": device.asset_tag, "hostname": device.hostname, "device_type": device.device_type, "brand": device.brand, "model": device.model, "department": device.department, "location": device.location, "ip_address": device.ip_address, "mac_address": device.mac_address, "inventory_status": device.inventory_status, "network_status": device.network_status, "last_scan": _value(scan.scanned_at) if scan else None, "response_time": scan.response_time if scan else None})
    return rows


def _network_rows(db, start_date, end_date, search):
    query = _date(db.query(NetworkScan), NetworkScan.scanned_at, start_date, end_date)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(NetworkScan.ip_address.ilike(term), NetworkScan.status.ilike(term)))
    scans = query.order_by(NetworkScan.scanned_at.desc()).all()
    devices = {str(row.id): row for row in db.query(Device).all()}
    return [{"id": str(scan.id), "device_id": str(scan.device_id), "device": devices.get(str(scan.device_id)).hostname if devices.get(str(scan.device_id)) else "Unavailable device", "ip_address": scan.ip_address, "status": scan.status, "response_time": scan.response_time, "scanned_at": _value(scan.scanned_at)} for scan in scans]


def _alert_rows(db, start_date, end_date, search):
    query = _date(db.query(Alert), Alert.created_at, start_date, end_date)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Alert.message.ilike(term), Alert.current_status.ilike(term)))
    devices = {str(row.id): row for row in db.query(Device).all()}
    return [{"id": str(row.id), "device_id": str(row.device_id), "device": devices.get(str(row.device_id)).hostname if devices.get(str(row.device_id)) else "Unavailable device", "department": devices.get(str(row.device_id)).department if devices.get(str(row.device_id)) else "Unassigned", "severity": "Critical" if row.current_status.lower() == "offline" else "Informational", "previous_status": row.previous_status, "current_status": row.current_status, "message": row.message, "acknowledged": row.acknowledged, "created_at": _value(row.created_at)} for row in query.order_by(Alert.created_at.desc()).all()]


def _ticket_rows(db, start_date, end_date, search):
    query = _date(db.query(Ticket), Ticket.created_at, start_date, end_date)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Ticket.title.ilike(term), Ticket.description.ilike(term), Ticket.status.ilike(term), Ticket.priority.ilike(term)))
    users = {row.id: row.username for row in db.query(User).all()}
    return [{"id": str(row.id), "title": row.title, "priority": row.priority, "status": row.status, "reporter": users.get(row.reported_by, "Unavailable user"), "assignee": users.get(row.assigned_to, "Unassigned") if row.assigned_to else "Unassigned", "created_at": _value(row.created_at), "updated_at": _value(row.updated_at)} for row in query.order_by(Ticket.created_at.desc()).all()]


def _user_rows(db, start_date, end_date, search):
    query = _date(db.query(User), User.created_at, start_date, end_date)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(User.username.ilike(term), User.email.ilike(term), User.role.ilike(term)))
    return [{"id": row.id, "username": row.username, "email": row.email, "role": row.role, "is_active": row.is_active, "created_at": _value(row.created_at), "updated_at": _value(row.updated_at)} for row in query.order_by(User.created_at.desc()).all()]


def _audit_rows(db, start_date, end_date, search):
    query = _date(db.query(AuditLog), AuditLog.created_at, start_date, end_date)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(AuditLog.actor.ilike(term), AuditLog.action.ilike(term), AuditLog.entity_type.ilike(term), AuditLog.description.ilike(term)))
    return [{"id": str(row.id), "actor": row.actor, "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id, "description": row.description, "created_at": _value(row.created_at)} for row in query.order_by(AuditLog.created_at.desc()).all()]


def _sort(rows, sort_by, sort_order):
    if not rows:
        return rows
    key = sort_by if sort_by in rows[0] else next(iter(rows[0]))
    return sorted(rows, key=lambda item: (item.get(key) is None, str(item.get(key, "")).lower()), reverse=sort_order == "desc")


def get_report(db: Session, report_name: str, start_date=None, end_date=None, search=None, status=None, department=None, category=None, page=1, page_size=25, sort_by=None, sort_order="asc"):
    _validate(report_name, start_date, end_date)
    loaders = {"devices": _device_rows, "network": _network_rows, "alerts": _alert_rows, "tickets": _ticket_rows, "users": _user_rows, "audit": _audit_rows}
    rows = loaders[report_name](db, start_date, end_date, search)
    if status:
        rows = [row for row in rows if str(row.get("network_status", row.get("inventory_status", row.get("status", row.get("current_status", "Active" if row.get("is_active") else "Inactive"))))).lower() == status.lower()]
    if department:
        rows = [row for row in rows if str(row.get("department", "Unassigned")).lower() == department.lower()]
    if category:
        rows = [row for row in rows if str(row.get("device_type", row.get("severity", row.get("priority", row.get("role", row.get("entity_type", "")))))).lower() == category.lower()]
    metrics: dict[str, Any] = {"total": len(rows)}
    charts: dict[str, list[dict[str, Any]]] = {}
    if report_name == "devices":
        charts = {"status": _distribution([row["network_status"] for row in rows]), "department": _distribution([row["department"] for row in rows]), "type": _distribution([row["device_type"] for row in rows])}
        metrics.update({"active": sum(row["inventory_status"].lower() == "active" for row in rows), "retired": sum(row["inventory_status"].lower() == "retired" for row in rows)})
    elif report_name == "network":
        charts["status"] = _distribution([row["status"] for row in rows])
        daily: dict[str, dict[str, Any]] = {}
        for row in rows:
            day = row["scanned_at"][:10]; bucket = daily.setdefault(day, {"name": day, "online": 0, "offline": 0, "unknown": 0, "total": 0})
            state = row["status"].lower(); bucket[state if state in ("online", "offline") else "unknown"] += 1; bucket["total"] += 1
        charts["trend"] = sorted(daily.values(), key=lambda item: item["name"])
        times = [row["response_time"] for row in rows if row["response_time"] is not None]
        metrics.update({"online": sum(row["status"].lower() == "online" for row in rows), "offline": sum(row["status"].lower() == "offline" for row in rows), "unknown": sum(row["status"].lower() not in ("online", "offline") for row in rows), "average_response_time": round(sum(times) / len(times), 2) if times else None})
    elif report_name == "alerts":
        charts = {"severity": _distribution([row["severity"] for row in rows]), "department": _distribution([row["department"] for row in rows])}
        daily = _distribution([row["created_at"][:10] for row in rows]); charts["daily"] = daily
        metrics.update({"open": sum(not row["acknowledged"] for row in rows), "acknowledged": sum(row["acknowledged"] for row in rows), "resolved": None, "critical": sum(row["severity"] == "Critical" for row in rows)})
    elif report_name == "tickets":
        charts = {"status": _distribution([row["status"] for row in rows]), "priority": _distribution([row["priority"] for row in rows]), "assignment": _distribution([row["assignee"] for row in rows]), "daily": _distribution([row["created_at"][:10] for row in rows])}
        metrics.update({"open": sum(row["status"] == "Open" for row in rows), "in_progress": sum(row["status"] == "In Progress" for row in rows), "closed": sum(row["status"] == "Closed" for row in rows)})
    elif report_name == "users":
        charts["role"] = _distribution([row["role"] for row in rows])
        metrics.update({"active": sum(row["is_active"] for row in rows), "inactive": sum(not row["is_active"] for row in rows), "admins": sum(row["role"] == "admin" for row in rows), "technicians": sum(row["role"] == "technician" for row in rows)})
    else:
        charts["entity"] = _distribution([row["entity_type"] for row in rows])
        metrics.update({"today": sum(row["created_at"][:10] == datetime.now(timezone.utc).date().isoformat() for row in rows), "user_activity": sum(row["entity_type"].lower() == "user" for row in rows), "device_activity": sum(row["entity_type"].lower() == "device" for row in rows), "ticket_activity": sum(row["entity_type"].lower() == "ticket" for row in rows)})
    rows = _sort(rows, sort_by, sort_order)
    items, total, pages = _page(rows, page, page_size)
    return {"report": report_name, "generated_at": datetime.now(timezone.utc), "items": items, "total": total, "page": page, "page_size": page_size, "pages": pages, "metrics": metrics, "charts": charts}


def export_csv(db: Session, report_name, start_date=None, end_date=None, search=None, status=None, department=None, category=None, sort_by=None, sort_order="asc"):
    report = get_report(db, report_name, start_date, end_date, search, status, department, category, 1, 1000000, sort_by, sort_order)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    generated = report["generated_at"]
    writer.writerow([REPORTS[report_name][0], generated.isoformat()])
    rows = report["items"]
    if rows:
        columns = list(rows[0].keys()); writer.writerow([column.replace("_", " ").title() for column in columns])
        for row in rows: writer.writerow([_csv_safe(row.get(column)) for column in columns])
    filename = f"hiop-{report_name}-report-{generated.strftime('%Y%m%d-%H%M%S')}.csv"
    return "\ufeff" + output.getvalue(), filename
