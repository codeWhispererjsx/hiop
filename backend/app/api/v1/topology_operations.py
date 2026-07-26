"""Administrative APIs for scheduled topology operations and safe reporting."""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.topology import Topology, TopologySnapshot
from app.models.topology_operations import (
    TopologyAlertEvent,
    TopologyAlertRule,
    TopologyOperationalRun,
)
from app.schemas.topology_operations import (
    AlertEventRead,
    AlertRuleRead,
    AlertRuleUpdate,
    AlertRuleWrite,
    MaintenanceRequest,
    ScheduleRead,
    ScheduleWrite,
)
from app.services.audit_service import create_audit_log
from app.services.scheduler_service import (
    pause_topology_jobs,
    register_topology_jobs,
    remove_topology_jobs,
    resume_topology_jobs,
    scheduler,
)
from app.services.topology_operational_service import TopologyOperationalService
from app.websocket.connection_manager import manager

router = APIRouter(prefix="/topology", tags=["Topology operations"])
admin = require_roles(["admin"])
reader = require_roles(["admin", "technician"])


def _topology(db: Session, topology_id: UUID) -> Topology:
    row = db.get(Topology, topology_id)
    if not row:
        raise HTTPException(404, "Topology was not found.")
    return row


def _page(query, schema, page: int, page_size: int):
    total = query.count()
    return {
        "items": [schema.model_validate(row) for row in query.offset((page - 1) * page_size).limit(page_size).all()],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/alert-rules")
def list_alert_rules(
    topology_id: UUID | None = None,
    enabled: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(reader),
):
    query = db.query(TopologyAlertRule)
    if topology_id:
        _topology(db, topology_id)
        query = query.filter(or_(TopologyAlertRule.topology_id == topology_id, TopologyAlertRule.topology_id.is_(None)))
    if enabled is not None:
        query = query.filter(TopologyAlertRule.enabled == enabled)
    return _page(query.order_by(TopologyAlertRule.name), AlertRuleRead, page, page_size)


@router.post("/alert-rules", response_model=AlertRuleRead, status_code=201)
def create_alert_rule(payload: AlertRuleWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    if payload.topology_id:
        _topology(db, payload.topology_id)
    row = TopologyAlertRule(**payload.model_dump(), created_by=actor.id, updated_by=actor.id)
    db.add(row)
    db.flush()
    create_audit_log(db, actor.username, "TOPOLOGY_ALERT_RULE_CREATED", "TopologyAlertRule", str(row.id), f"Created disabled-by-default topology alert rule '{row.name}'.")
    db.commit()
    db.refresh(row)
    return row


@router.get("/alert-rules/{rule_id}", response_model=AlertRuleRead)
def get_alert_rule(rule_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    row = db.get(TopologyAlertRule, rule_id)
    if not row:
        raise HTTPException(404, "Topology alert rule was not found.")
    return row


@router.patch("/alert-rules/{rule_id}", response_model=AlertRuleRead)
def update_alert_rule(rule_id: UUID, payload: AlertRuleUpdate, db: Session = Depends(get_db), actor=Depends(admin)):
    row = get_alert_rule(rule_id, db)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    row.updated_by = actor.id
    create_audit_log(db, actor.username, "TOPOLOGY_ALERT_RULE_UPDATED", "TopologyAlertRule", str(row.id), f"Updated topology alert rule '{row.name}'.")
    db.commit()
    db.refresh(row)
    return row


@router.post("/alert-rules/{rule_id}/enable", response_model=AlertRuleRead)
def enable_alert_rule(rule_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_alert_rule(rule_id, AlertRuleUpdate(enabled=True), db, actor)


@router.post("/alert-rules/{rule_id}/disable", response_model=AlertRuleRead)
def disable_alert_rule(rule_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    return update_alert_rule(rule_id, AlertRuleUpdate(enabled=False), db, actor)


@router.post("/alert-rules/{rule_id}/preview")
def preview_alert_rule(rule_id: UUID, topology_id: UUID, db: Session = Depends(get_db), _=Depends(admin)):
    row = get_alert_rule(rule_id, db)
    if row.topology_id and row.topology_id != topology_id:
        raise HTTPException(409, "Alert rule belongs to another topology.")
    _topology(db, topology_id)
    result = TopologyOperationalService(db).evaluate_alerts(topology_id, preview=True)
    return next((item for item in result.get("items", []) if item["rule_id"] == str(rule_id)), {"rule_id": str(rule_id), "would_trigger": False})


@router.get("/alerts")
def list_alert_events(
    topology_id: UUID | None = None,
    is_open: bool | None = None,
    severity: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(reader),
):
    query = db.query(TopologyAlertEvent)
    if topology_id:
        _topology(db, topology_id)
        query = query.filter_by(topology_id=topology_id)
    if is_open is not None:
        query = query.filter_by(is_open=is_open)
    if severity:
        query = query.filter_by(severity=severity)
    return _page(query.order_by(TopologyAlertEvent.last_seen_at.desc()), AlertEventRead, page, page_size)


@router.get("/retention/preview")
def retention_preview(db: Session = Depends(get_db), _=Depends(admin)):
    return TopologyOperationalService(db).retention_preview()


@router.post("/retention/cleanup")
def retention_cleanup(batch_size: int = Query(500, ge=1, le=5000), db: Session = Depends(get_db), actor=Depends(admin)):
    return TopologyOperationalService(db).cleanup(actor, batch_size)


@router.get("/{topology_id}/schedule", response_model=ScheduleRead)
def get_schedule(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    return TopologyOperationalService(db).schedule(topology_id)


@router.put("/{topology_id}/schedule", response_model=ScheduleRead)
def put_schedule(topology_id: UUID, payload: ScheduleWrite, db: Session = Depends(get_db), actor=Depends(admin)):
    topology = _topology(db, topology_id)
    row = TopologyOperationalService(db).schedule(topology_id)
    if payload.enabled and not topology.enabled:
        raise HTTPException(409, "A disabled topology cannot be scheduled.")
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    row.last_scheduler_reconciliation_at = datetime.now(timezone.utc)
    create_audit_log(db, actor.username, "TOPOLOGY_SCHEDULE_UPDATED", "Topology", str(topology_id), "Updated topology schedule configuration.")
    db.commit()
    remove_topology_jobs(str(topology_id))
    if row.enabled:
        register_topology_jobs(str(topology_id))
    db.refresh(row)
    manager.broadcast_from_thread({"type": "topology_schedule_updated", "topology_id": str(topology_id)})
    return row


@router.post("/{topology_id}/schedule/pause")
def pause_schedule(topology_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    _topology(db, topology_id)
    count = pause_topology_jobs(str(topology_id))
    create_audit_log(db, actor.username, "TOPOLOGY_SCHEDULE_PAUSED", "Topology", str(topology_id), f"Paused {count} topology jobs.")
    db.commit()
    return {"paused_jobs": count}


@router.post("/{topology_id}/schedule/resume")
def resume_schedule(topology_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    _topology(db, topology_id)
    count = resume_topology_jobs(str(topology_id))
    create_audit_log(db, actor.username, "TOPOLOGY_SCHEDULE_RESUMED", "Topology", str(topology_id), f"Resumed {count} topology jobs.")
    db.commit()
    return {"resumed_jobs": count}


@router.get("/{topology_id}/scheduler-status")
def scheduler_status(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    prefix = f"topology_{topology_id}_"
    jobs = [
        {"id": job.id, "next_run_time": job.next_run_time, "pending": job.pending}
        for job in scheduler.get_jobs() if job.id.startswith(prefix)
    ]
    return {"scheduler_running": scheduler.running, "jobs": jobs}


@router.post("/{topology_id}/maintenance/start", response_model=ScheduleRead)
def start_maintenance(topology_id: UUID, payload: MaintenanceRequest, db: Session = Depends(get_db), actor=Depends(admin)):
    _topology(db, topology_id)
    row = TopologyOperationalService(db).schedule(topology_id)
    row.maintenance_mode = True
    row.maintenance_reason = payload.reason
    row.maintenance_started_at = datetime.now(timezone.utc)
    row.maintenance_ends_at = payload.ends_at
    row.maintenance_started_by = actor.id
    create_audit_log(db, actor.username, "TOPOLOGY_MAINTENANCE_STARTED", "Topology", str(topology_id), "Started topology alert-suppression maintenance mode.")
    db.commit()
    db.refresh(row)
    return row


@router.post("/{topology_id}/maintenance/end", response_model=ScheduleRead)
def end_maintenance(topology_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    _topology(db, topology_id)
    row = TopologyOperationalService(db).schedule(topology_id)
    row.maintenance_mode = False
    row.maintenance_ends_at = datetime.now(timezone.utc)
    create_audit_log(db, actor.username, "TOPOLOGY_MAINTENANCE_ENDED", "Topology", str(topology_id), "Ended topology maintenance mode.")
    db.commit()
    db.refresh(row)
    return row


@router.get("/{topology_id}/health")
def topology_health(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return TopologyOperationalService(db).health(topology_id)


@router.get("/{topology_id}/analytics")
def topology_analytics(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    _topology(db, topology_id)
    return TopologyOperationalService(db).analytics(topology_id)


@router.get("/{topology_id}/operational-runs")
def operational_runs(
    topology_id: UUID,
    status: str | None = None,
    run_type: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(reader),
):
    _topology(db, topology_id)
    query = db.query(TopologyOperationalRun).filter_by(topology_id=topology_id)
    if status:
        query = query.filter_by(status=status)
    if run_type:
        query = query.filter_by(run_type=run_type)
    total = query.count()
    rows = query.order_by(TopologyOperationalRun.started_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": rows, "total": total, "page": page, "page_size": page_size}


@router.get("/{topology_id}/reports/summary")
def report_summary(topology_id: UUID, db: Session = Depends(get_db), _=Depends(reader)):
    return {
        "health": TopologyOperationalService(db).health(topology_id),
        "analytics": TopologyOperationalService(db).analytics(topology_id),
        "open_alerts": db.query(TopologyAlertEvent).filter_by(topology_id=topology_id, is_open=True).count(),
        "failed_runs": db.query(TopologyOperationalRun).filter_by(topology_id=topology_id, status="failed").count(),
    }


@router.get("/{topology_id}/exports/{kind}.csv")
def export_csv(topology_id: UUID, kind: str, db: Session = Depends(get_db), _=Depends(reader)):
    topology = _topology(db, topology_id)
    content = TopologyOperationalService(db).export_csv(topology_id, kind)
    filename = f"hiop-topology-{kind}-{str(topology.id)[:8]}.csv"
    return Response(
        content="\ufeff" + content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"},
    )


@router.post("/{topology_id}/snapshots/{snapshot_id}/baseline")
def set_baseline(topology_id: UUID, snapshot_id: UUID, db: Session = Depends(get_db), actor=Depends(admin)):
    _topology(db, topology_id)
    snapshot = db.get(TopologySnapshot, snapshot_id)
    if not snapshot or snapshot.topology_id != topology_id:
        raise HTTPException(404, "Snapshot was not found in this topology.")
    db.query(TopologySnapshot).filter_by(topology_id=topology_id).update({"is_operational_baseline": False})
    snapshot.is_operational_baseline = True
    snapshot.is_protected = True
    create_audit_log(db, actor.username, "TOPOLOGY_BASELINE_CHANGED", "TopologySnapshot", str(snapshot.id), "Set the protected operational baseline snapshot.")
    db.commit()
    manager.broadcast_from_thread({"type": "topology_baseline_changed", "topology_id": str(topology_id), "snapshot_id": str(snapshot.id)})
    return {"snapshot_id": snapshot.id, "is_operational_baseline": True, "is_protected": True}
