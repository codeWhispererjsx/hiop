import csv
import io
import json
import re
import socket
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import allowed_property_ids, organization_context
from app.models.audit_log import AuditLog
from app.models.device import Device
from app.models.hierarchy import Floor, Property
from app.models.local_agent import AgentJob, AgentMaintenanceRule, LocalAgentRegistration
from app.models.user import User
from app.services.audit_service import create_audit_log

router = APIRouter(prefix="/reports", tags=["System Maintenance"])
rules_router = APIRouter(prefix="/automation/rules", tags=["Maintenance Automation"])
admin = require_roles(["admin"])
reader = require_roles(["platformadmin", "admin", "technician", "viewer"])
RuleAction = Literal["RESTART", "SHUTDOWN", "TRIGGER_WINDOWS_UPDATE", "WAKE_ON_LAN"]


class RuleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    property_id: UUID | None = None
    criteria: dict = Field(default_factory=dict)
    schedule: dict
    action: RuleAction
    enabled: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Rule name must contain at least two non-space characters.")
        return value

    @field_validator("schedule")
    @classmethod
    def validate_schedule(cls, value):
        if set(value) - {"frequency", "time", "weekday", "timezone"}:
            raise ValueError("Schedule supports only frequency, time, weekday, and timezone.")
        if value.get("frequency") not in {"daily", "weekly"}:
            raise ValueError("Schedule frequency must be daily or weekly.")
        schedule_time = value.get("time")
        timezone_name = value.get("timezone")
        if not isinstance(schedule_time, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", schedule_time):
            raise ValueError("Schedule time must use 24-hour HH:MM format.")
        if not isinstance(timezone_name, str) or not timezone_name:
            raise ValueError("Schedule needs a valid IANA timezone.")
        try:
            time.fromisoformat(schedule_time)
            ZoneInfo(timezone_name)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Schedule needs a valid local time and IANA timezone.") from exc
        weekday = value.get("weekday")
        if value["frequency"] == "weekly" and (
            not isinstance(weekday, int) or isinstance(weekday, bool) or weekday not in range(7)
        ):
            raise ValueError("Weekly schedules need weekday 0-6 (Monday-Sunday).")
        if value["frequency"] == "daily" and "weekday" in value:
            raise ValueError("Daily schedules must not include a weekday.")
        return value

    @field_validator("criteria")
    @classmethod
    def validate_criteria(cls, value):
        allowed = {"uptime_hours", "update_age_days", "department", "location", "hostname_contains"}
        if set(value) - allowed:
            raise ValueError("Unsupported rule criteria.")
        for field in ("uptime_hours", "update_age_days"):
            if field in value and (
                not isinstance(value[field], int) or isinstance(value[field], bool)
                or not 1 <= value[field] <= 8760
            ):
                raise ValueError(f"{field} must be a whole number between 1 and 8760.")
        for field in ("department", "location", "hostname_contains"):
            if field in value and (
                not isinstance(value[field], str) or not value[field].strip() or len(value[field].strip()) > 120
            ):
                raise ValueError(f"{field} must be at most 120 characters.")
        if not value:
            raise ValueError("Add at least one device condition before saving a rule.")
        return {
            key: value[key].strip() if isinstance(value[key], str) else value[key]
            for key in value
        }


def _rule_json(row: AgentMaintenanceRule, db: Session):
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "property_id": str(row.property_id) if row.property_id else None,
        "criteria": json.loads(row.criteria),
        "schedule": json.loads(row.schedule),
        "action": row.action,
        "enabled": row.enabled,
        "last_run_at": row.last_run_at,
        "affected_count": _matched_devices(db, row.organization_id, row.property_id, json.loads(row.criteria))[0],
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _matched_devices(db: Session, org_id, property_id, criteria):
    query = db.query(LocalAgentRegistration, Device).join(
        Device, LocalAgentRegistration.device_id == Device.id
    ).join(Property, Device.property_id == Property.id).filter(
        Property.organization_id == org_id,
        Device.inventory_status != "Retired",
        LocalAgentRegistration.revoked_at.is_(None),
        LocalAgentRegistration.retired_at.is_(None),
    )
    if property_id:
        query = query.filter(Device.property_id == property_id)
    matches = []
    now = datetime.now(timezone.utc)
    for agent, device in query.all():
        if criteria.get("uptime_hours") and (agent.uptime_seconds or 0) < criteria["uptime_hours"] * 3600:
            continue
        if criteria.get("update_age_days"):
            if not agent.last_update or now - agent.last_update <= timedelta(days=criteria["update_age_days"]):
                continue
        if criteria.get("department") and (device.department or "").casefold() != criteria["department"].casefold():
            continue
        if criteria.get("location") and (device.location or "").casefold() != criteria["location"].casefold():
            continue
        if criteria.get("hostname_contains") and criteria["hostname_contains"].casefold() not in (agent.hostname or agent.name).casefold():
            continue
        matches.append((agent, device))
    return len(matches), matches


def _authorized_property(db: Session, user: User, org_id, property_id):
    if property_id is not None:
        if property_id not in allowed_property_ids(db, user, org_id):
            raise HTTPException(403, "Property is outside your permitted scope")
        if not db.query(Property.id).filter_by(id=property_id, organization_id=org_id).first():
            raise HTTPException(404, "Property not found")


@router.get("/system-health")
def system_health(db: Session = Depends(get_db), user: User = Depends(reader), org=Depends(organization_context)):
    allowed = allowed_property_ids(db, user, org)
    device_rows = db.query(Device, Floor).join(Property, Device.property_id == Property.id).outerjoin(
        Floor, Device.floor_id == Floor.id
    ).filter(
        Property.organization_id == org,
        Device.property_id.in_(allowed),
        Device.inventory_status != "Retired",
    ).all()
    devices = [device for device, _ in device_rows]
    floors = {device.id: floor.display_name or floor.name for device, floor in device_rows if floor}
    agents = {
        row.device_id: row for row in db.query(LocalAgentRegistration).filter(
            LocalAgentRegistration.organization_id == org,
            LocalAgentRegistration.property_id.in_(allowed),
            LocalAgentRegistration.device_id.is_not(None),
            LocalAgentRegistration.revoked_at.is_(None),
        ).order_by(LocalAgentRegistration.last_heartbeat.desc()).all()
    }
    now = datetime.now(timezone.utc)
    rows = []
    for device in devices:
        agent = agents.get(device.id)
        heartbeat = agent.last_heartbeat if agent else None
        online = bool(heartbeat and (now - heartbeat).total_seconds() <= 180)
        uptime = agent.uptime_seconds if agent else None
        last_update = agent.last_update if agent else None
        offline_long = bool(heartbeat and now - heartbeat > timedelta(hours=24)) or (agent is not None and heartbeat is None)
        if not agent:
            status_text = "No agent"
        elif offline_long:
            status_text = "Offline Long"
        elif not online:
            status_text = "Offline"
        elif uptime is not None and uptime > 48 * 3600:
            status_text = "Needs Restart"
        elif last_update and now - last_update > timedelta(days=7):
            status_text = "Needs Update"
        elif not last_update:
            status_text = "Update Data Unavailable"
        else:
            status_text = "Healthy"
        rows.append({
            "device_id": str(device.id),
            "agent_id": str(agent.id) if agent else None,
            "hostname": (agent.hostname or device.hostname) if agent else device.hostname,
            "assigned_to": agent.logged_user if agent else None,
            "department": device.department,
            "location": device.location,
            "floor": floors.get(device.id),
            "ip_address": (agent.ip_address or device.ip_address) if agent else device.ip_address,
            "online": online,
            "last_seen": heartbeat,
            "uptime_seconds": uptime,
            "last_update": last_update,
            "status": status_text,
        })
    restarts = db.query(AgentJob).filter(
        AgentJob.organization_id == org,
        AgentJob.property_id.in_(allowed),
        AgentJob.job_type == "DEVICE_ACTION",
        AgentJob.status == "completed",
        AgentJob.created_at >= now - timedelta(days=7),
    ).all()
    action_jobs = [(job, json.loads(job.payload)) for job in restarts]
    for row in rows:
        agent = agents.get(UUID(row["device_id"]))
        matching = [(job, payload) for job, payload in action_jobs if agent and job.agent_id == agent.id]
        row["last_restart"] = next((job.completed_at for job, payload in matching if payload.get("action") == "RESTART"), None)
        row["last_cool_off"] = next((job.completed_at for job, payload in matching if payload.get("action") == "SHUTDOWN"), None)
    total = len(rows)
    online = [row for row in rows if row["online"]]
    updates = sum(bool(row["last_update"] and now - row["last_update"] > timedelta(days=7)) for row in rows)
    restarts_needed = sum((row["uptime_seconds"] or 0) > 48 * 3600 for row in online)
    hygiene = sum(row["status"] == "Healthy" for row in rows) / total * 100 if total else 0
    cooled = 0
    for row in rows:
        if not row["last_cool_off"]:
            continue
        device = next((item for item in devices if str(item.id) == row["device_id"]), None)
        property_row = db.get(Property, device.property_id) if device else None
        zone = ZoneInfo(property_row.timezone if property_row else "UTC")
        local_now = now.astimezone(zone)
        start_day = local_now.date() - timedelta(days=1) if local_now.hour < 6 else local_now.date()
        start = datetime.combine(start_day, time(21), tzinfo=zone)
        end = datetime.combine(start_day + timedelta(days=1), time(6), tzinfo=zone)
        cooled += int(start <= row["last_cool_off"].astimezone(zone) <= min(end, local_now))
    return {
        "summary": {
            "total_devices": total,
            "updates_needed": updates,
            "restarts_needed": restarts_needed,
            "cooled_off_last_night": cooled,
            "hygiene_score": round(hygiene),
            "online": sum(row["online"] for row in rows),
        },
        "devices": rows,
    }


@router.get("/maintenance-log")
def maintenance_log(
    range: Literal["7d", "30d", "custom"] = Query("7d"),
    db: Session = Depends(get_db),
    user: User = Depends(reader),
    org=Depends(organization_context),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    now = datetime.now(timezone.utc)
    if range == "custom":
        if not start_date or not end_date or start_date > end_date:
            raise HTTPException(422, "Custom range needs a valid start and end date.")
        if (end_date - start_date).days > 365:
            raise HTTPException(422, "Custom range cannot exceed 366 days.")
        cutoff = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_exclusive = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
    else:
        if start_date or end_date:
            raise HTTPException(422, "Start and end dates are supported only for a custom range.")
        cutoff = now - timedelta(days=7 if range == "7d" else 30)
        end_exclusive = now
    allowed = allowed_property_ids(db, user, org)
    jobs = db.query(AgentJob, LocalAgentRegistration).join(
        LocalAgentRegistration, AgentJob.agent_id == LocalAgentRegistration.id
    ).filter(
        AgentJob.organization_id == org,
        AgentJob.property_id.in_(allowed),
        AgentJob.job_type == "DEVICE_ACTION",
        AgentJob.created_at >= cutoff,
        AgentJob.created_at < end_exclusive,
    ).order_by(AgentJob.created_at.desc()).limit(1000).all()
    rows = []
    for job, agent in jobs:
        payload = json.loads(job.payload)
        action = payload.get("action", "Unknown")
        rule = payload.get("rule_name")
        rows.append({
            "date_time": job.created_at,
            "hostname": agent.hostname or agent.name,
            "action": action,
            "triggered_by": f"Automation Rule: {rule}" if rule else job.created_by or "Manual",
            "result": job.status,
            "notes": job.error,
        })
    wake_events = db.query(AuditLog).filter(
        AuditLog.organization_id == org,
        AuditLog.property_id.in_(allowed),
        AuditLog.entity_type == "Device",
        AuditLog.action.in_(("DEVICE_ACTION_WOL", "DEVICE_ACTION_WOL_FAILED", "MAINTENANCE_RULE_WOL_SENT", "MAINTENANCE_RULE_WOL_FAILED")),
        AuditLog.created_at >= cutoff,
        AuditLog.created_at < end_exclusive,
    ).order_by(AuditLog.created_at.desc()).limit(1000).all()
    device_ids = []
    for event in wake_events:
        try:
            device_ids.append(UUID(event.entity_id))
        except ValueError:
            continue
    wake_devices = {
        str(device.id): device for device in db.query(Device).filter(
            Device.id.in_(device_ids),
            Device.property_id.in_(allowed),
        ).all()
    } if device_ids else {}
    for event in wake_events:
        device = wake_devices.get(event.entity_id)
        rows.append({
            "date_time": event.created_at,
            "hostname": device.hostname if device else event.entity_id,
            "action": "WAKE_ON_LAN",
            "triggered_by": event.actor if event.actor.startswith("Automation Rule:") else event.actor or "Manual",
            "result": "failed" if event.action.endswith("_FAILED") else "completed",
            "notes": event.description,
        })
    rows.sort(key=lambda row: row["date_time"], reverse=True)
    return {"items": rows}


@router.get("/maintenance-log/export")
def export_maintenance_log(
    range: Literal["7d", "30d", "custom"] = Query("7d"),
    db: Session = Depends(get_db),
    user: User = Depends(reader),
    org=Depends(organization_context),
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
):
    rows = maintenance_log(range, db, user, org, start_date, end_date)["items"]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["date_time", "hostname", "action", "triggered_by", "result", "notes"])
    writer.writeheader()
    writer.writerows(rows)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="system-maintenance.csv"'})


@rules_router.get("")
def list_rules(db: Session = Depends(get_db), user: User = Depends(reader), org=Depends(organization_context)):
    allowed = allowed_property_ids(db, user, org)
    rows = db.query(AgentMaintenanceRule).filter(
        AgentMaintenanceRule.organization_id == org,
        (AgentMaintenanceRule.property_id.is_(None) | AgentMaintenanceRule.property_id.in_(allowed)),
    ).order_by(AgentMaintenanceRule.created_at.desc()).all()
    return {"items": [_rule_json(row, db) for row in rows]}


@rules_router.post("", status_code=201)
def create_rule(body: RuleWrite, db: Session = Depends(get_db), actor: User = Depends(admin), org=Depends(organization_context)):
    _authorized_property(db, actor, org, body.property_id)
    row = AgentMaintenanceRule(
        organization_id=org,
        property_id=body.property_id,
        name=body.name.strip(),
        description=body.description,
        criteria=json.dumps(body.criteria, separators=(",", ":")),
        schedule=json.dumps(body.schedule, separators=(",", ":")),
        action=body.action,
        enabled=body.enabled,
        created_by=actor.id,
    )
    db.add(row)
    db.flush()
    create_audit_log(db, actor.username, "MAINTENANCE_RULE_CREATED", "AgentMaintenanceRule", str(row.id), f"Created maintenance rule {row.name}", organization_id=org, property_id=row.property_id)
    db.commit()
    db.refresh(row)
    return _rule_json(row, db)


@rules_router.put("/{rule_id}")
def update_rule(rule_id: UUID, body: RuleWrite, db: Session = Depends(get_db), actor: User = Depends(admin), org=Depends(organization_context)):
    row = db.query(AgentMaintenanceRule).filter_by(id=rule_id, organization_id=org).first()
    if not row or (row.property_id and row.property_id not in allowed_property_ids(db, actor, org)):
        raise HTTPException(404, "Maintenance rule not found")
    _authorized_property(db, actor, org, body.property_id)
    row.name = body.name.strip()
    row.description = body.description
    row.property_id = body.property_id
    row.criteria = json.dumps(body.criteria, separators=(",", ":"))
    row.schedule = json.dumps(body.schedule, separators=(",", ":"))
    row.action = body.action
    row.enabled = body.enabled
    row.updated_at = datetime.now(timezone.utc)
    create_audit_log(db, actor.username, "MAINTENANCE_RULE_UPDATED", "AgentMaintenanceRule", str(row.id), f"Updated maintenance rule {row.name}; enabled={row.enabled}", organization_id=org, property_id=row.property_id)
    db.commit()
    db.refresh(row)
    return _rule_json(row, db)


@rules_router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: UUID, db: Session = Depends(get_db), actor: User = Depends(admin), org=Depends(organization_context)):
    row = db.query(AgentMaintenanceRule).filter_by(id=rule_id, organization_id=org).first()
    if not row or (row.property_id and row.property_id not in allowed_property_ids(db, actor, org)):
        raise HTTPException(404, "Maintenance rule not found")
    create_audit_log(db, actor.username, "MAINTENANCE_RULE_DELETED", "AgentMaintenanceRule", str(row.id), f"Deleted maintenance rule {row.name}", organization_id=org, property_id=row.property_id)
    db.delete(row)
    db.commit()


def run_maintenance_rules():
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rules = db.query(AgentMaintenanceRule).filter_by(enabled=True).all()
        for rule in rules:
            schedule = json.loads(rule.schedule)
            local_now = now.astimezone(ZoneInfo(schedule["timezone"]))
            if local_now.strftime("%H:%M") != schedule["time"]:
                continue
            if schedule["frequency"] == "weekly" and local_now.weekday() != schedule["weekday"]:
                continue
            if rule.last_run_at and rule.last_run_at.astimezone(ZoneInfo(schedule["timezone"])).date() == local_now.date():
                continue
            _, targets = _matched_devices(db, rule.organization_id, rule.property_id, json.loads(rule.criteria))
            for agent, device in targets:
                if rule.action == "WAKE_ON_LAN":
                    mac = re.sub(r"[^0-9a-fA-F]", "", device.mac_address or "")
                    if len(mac) != 12:
                        create_audit_log(
                            db, f"Automation Rule: {rule.name}", "MAINTENANCE_RULE_WOL_FAILED",
                            "Device", str(device.id), "Wake-on-LAN requires a valid device MAC address.",
                            organization_id=rule.organization_id, property_id=rule.property_id or device.property_id,
                        )
                        continue
                    try:
                        packet = b"\xff" * 6 + bytes.fromhex(mac) * 16
                        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                            sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                            sender.sendto(packet, ("255.255.255.255", 9))
                    except OSError as exc:
                        create_audit_log(
                            db, f"Automation Rule: {rule.name}", "MAINTENANCE_RULE_WOL_FAILED",
                            "Device", str(device.id), f"Wake-on-LAN send failed: {exc}",
                            organization_id=rule.organization_id, property_id=rule.property_id or device.property_id,
                        )
                        continue
                    create_audit_log(
                        db, f"Automation Rule: {rule.name}", "MAINTENANCE_RULE_WOL_SENT",
                        "Device", str(device.id), "Wake-on-LAN packet sent.",
                        organization_id=rule.organization_id, property_id=rule.property_id or device.property_id,
                    )
                    continue
                online = agent_view_for_rule(agent, now)
                if not online:
                    continue
                db.add(AgentJob(
                    agent_id=agent.id,
                    organization_id=agent.organization_id,
                    property_id=agent.property_id,
                    job_type="DEVICE_ACTION",
                    payload=json.dumps({"action": rule.action, "rule_id": str(rule.id), "rule_name": rule.name}),
                    timeout_seconds=30,
                ))
            rule.last_run_at = now
            create_audit_log(db, "HIOP Scheduler", "MAINTENANCE_RULE_EXECUTED", "AgentMaintenanceRule", str(rule.id), f"Ran {rule.name} against {len(targets)} matching endpoints", organization_id=rule.organization_id, property_id=rule.property_id)
        db.commit()
    finally:
        db.close()


def agent_view_for_rule(agent: LocalAgentRegistration, now: datetime) -> bool:
    return bool(not agent.revoked_at and not agent.retired_at and agent.last_heartbeat and (now - agent.last_heartbeat).total_seconds() <= 120)
