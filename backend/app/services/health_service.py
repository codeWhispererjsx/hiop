import logging
from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import and_, func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models.system_health import HealthEvent, JobExecution, NotificationDelivery, SystemHealthSnapshot
from app.models.local_agent import LocalAgentRegistration
from app.models.discovery_intelligence import DiscoveryJob, DiscoveryResult
from app.models.snmp import SNMPPollRun
from app.models.network_scan import NetworkScan

logger = logging.getLogger(__name__)

HealthStatus = Literal["HEALTHY", "DEGRADED", "STALE", "FAILED", "NOT_CONFIGURED", "UNKNOWN"]

COMPONENT_FRESHNESS = {
    "api": 60,  # seconds
    "database": 60,
    "scheduler": 120,
    "discovery": 3600,  # 1 hour
    "monitoring": 300,  # 5 minutes
    "alert_processing": 300,
    "notifications": 600,  # 10 minutes
    "agent": 600,  # 10 minutes
}


def record_health(
    db: Session,
    component: str,
    status: HealthStatus,
    last_success: datetime | None = None,
    last_failure: datetime | None = None,
    details: str | None = None,
    organization_id: UUID | None = None,
    property_id: UUID | None = None,
) -> SystemHealthSnapshot | None:
    """Record or update health state for a component. Returns None if tables don't exist."""
    try:
        now = datetime.now(timezone.utc)
        
        # Get current state
        existing = db.query(SystemHealthSnapshot).filter(
            SystemHealthSnapshot.component == component,
            SystemHealthSnapshot.organization_id == organization_id,
            SystemHealthSnapshot.property_id == property_id,
        ).first()
    
        previous_status = existing.status if existing else None
        
        # Update or create
        if existing:
            existing.status = status
            existing.last_success = last_success
            existing.last_failure = last_failure
            existing.last_check = now
            existing.details = details
        else:
            existing = SystemHealthSnapshot(
                component=component,
                status=status,
                last_success=last_success,
                last_failure=last_failure,
                last_check=now,
                details=details,
                organization_id=organization_id,
                property_id=property_id,
            )
            db.add(existing)
        
        # Record transition if status changed
        if previous_status != status:
            event = HealthEvent(
                component=component,
                previous_status=previous_status,
                new_status=status,
                reason=details,
                organization_id=organization_id,
                property_id=property_id,
            )
            db.add(event)
            logger.info(f"Health transition: {component} {previous_status} -> {status}")
        
        db.commit()
        db.refresh(existing)
        return existing
    except (OperationalError, ProgrammingError) as e:
        # Tables don't exist yet (migrations not applied)
        logger.warning(f"Health tables not available yet: {e}")
        db.rollback()
        return None


def get_health(db: Session, component: str, organization_id: UUID | None = None, property_id: UUID | None = None) -> SystemHealthSnapshot | None:
    """Get current health state for a component. Returns None if tables don't exist."""
    try:
        return db.query(SystemHealthSnapshot).filter(
            SystemHealthSnapshot.component == component,
            SystemHealthSnapshot.organization_id == organization_id,
            SystemHealthSnapshot.property_id == property_id,
        ).first()
    except (OperationalError, ProgrammingError) as e:
        # Tables don't exist yet (migrations not applied)
        logger.warning(f"Health tables not available yet: {e}")
        return None


def record_job_execution(
    db: Session,
    job_id: str,
    job_type: str,
    status: str,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    error: str | None = None,
    result_summary: str | None = None,
    correlation_id: str | None = None,
    organization_id: UUID | None = None,
    property_id: UUID | None = None,
) -> JobExecution | None:
    """Record job execution history. Returns None if tables don't exist."""
    try:
        if started_at is None:
            started_at = datetime.now(timezone.utc)
        
        duration = None
        if completed_at and started_at:
            duration = int((completed_at - started_at).total_seconds())
        
        execution = JobExecution(
            job_id=job_id,
            job_type=job_type,
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration,
            error=error,
            result_summary=result_summary,
            correlation_id=correlation_id,
            organization_id=organization_id,
            property_id=property_id,
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        return execution
    except (OperationalError, ProgrammingError) as e:
        # Tables don't exist yet (migrations not applied)
        logger.warning(f"Job execution tables not available yet: {e}")
        db.rollback()
        return None


def get_last_job_execution(
    db: Session,
    job_type: str,
    organization_id: UUID | None = None,
    property_id: UUID | None = None,
) -> JobExecution | None:
    """Get the most recent execution for a job type. Returns None if tables don't exist."""
    try:
        return db.query(JobExecution).filter(
            JobExecution.job_type == job_type,
            JobExecution.organization_id == organization_id,
            JobExecution.property_id == property_id,
        ).order_by(JobExecution.started_at.desc()).first()
    except (OperationalError, ProgrammingError) as e:
        # Tables don't exist yet (migrations not applied)
        logger.warning(f"Job execution tables not available yet: {e}")
        return None


def check_job_staleness(db: Session, job_type: str, freshness_seconds: int, organization_id: UUID | None = None, property_id: UUID | None = None) -> tuple[HealthStatus, str | None]:
    """Check if a job is stale based on its last successful execution."""
    last = get_last_job_execution(db, job_type, organization_id, property_id)
    
    if not last:
        return "NOT_CONFIGURED", "No job execution recorded"
    
    if last.status == "FAILED":
        return "FAILED", last.error or "Last execution failed"
    
    if last.status == "RUNNING":
        # Check if running too long
        if last.started_at and (datetime.now(timezone.utc) - last.started_at).total_seconds() > freshness_seconds * 2:
            return "STALE", f"Job running for {(datetime.now(timezone.utc) - last.started_at).total_seconds():.0f}s, expected < {freshness_seconds * 2}s"
        return "HEALTHY", "Job currently running"
    
    if last.completed_at:
        age = (datetime.now(timezone.utc) - last.completed_at).total_seconds()
        if age > freshness_seconds:
            return "STALE", f"Last successful run {age:.0f}s ago, expected within {freshness_seconds}s"
        return "HEALTHY", f"Last successful run {age:.0f}s ago"
    
    return "UNKNOWN", "Job has no completion time"


def update_scheduler_health(db: Session, is_running: bool, last_job_success: datetime | None = None, last_job_failure: datetime | None = None) -> SystemHealthSnapshot:
    """Update scheduler health based on actual execution evidence."""
    if not is_running:
        return record_health(db, "scheduler", "FAILED", last_failure=datetime.now(timezone.utc), details="Scheduler process not running")
    
    # Get the most recent successful job execution across all job types
    from app.models.system_health import JobExecution
    latest_success = db.query(JobExecution).filter(
        JobExecution.status == "SUCCESS",
    ).order_by(JobExecution.completed_at.desc()).first()
    
    if latest_success and latest_success.completed_at:
        last_job_success = latest_success.completed_at
    
    if last_job_success:
        age = (datetime.now(timezone.utc) - last_job_success).total_seconds()
        if age > COMPONENT_FRESHNESS["scheduler"]:
            return record_health(db, "scheduler", "STALE", last_success=last_job_success, details=f"No successful job in {age:.0f}s")
        return record_health(db, "scheduler", "HEALTHY", last_success=last_job_success, details=f"Last successful job {age:.0f}s ago")
    
    return record_health(db, "scheduler", "UNKNOWN", details="Scheduler running but no job history")


def update_discovery_health(db: Session, organization_id: UUID | None = None, property_id: UUID | None = None) -> SystemHealthSnapshot:
    """Update discovery health based on actual discovery execution."""
    # Check for recent discovery results
    latest_result = db.query(DiscoveryResult).filter(
        DiscoveryResult.organization_id == organization_id if organization_id else True,
        DiscoveryResult.property_id == property_id if property_id else True,
    ).order_by(DiscoveryResult.created_at.desc()).first()
    
    if not latest_result:
        return record_health(db, "discovery", "NOT_CONFIGURED", organization_id=organization_id, property_id=property_id, details="No discovery results found")
    
    age = (datetime.now(timezone.utc) - latest_result.created_at).total_seconds()
    if age > COMPONENT_FRESHNESS["discovery"]:
        return record_health(db, "discovery", "STALE", last_success=latest_result.created_at, organization_id=organization_id, property_id=property_id, details=f"Last discovery {age:.0f}s ago")
    
    return record_health(db, "discovery", "HEALTHY", last_success=latest_result.created_at, organization_id=organization_id, property_id=property_id)


def update_monitoring_health(db: Session, organization_id: UUID | None = None, property_id: UUID | None = None) -> SystemHealthSnapshot:
    """Update monitoring health based on actual monitoring data freshness."""
    # Check for recent network scans
    latest_scan = db.query(NetworkScan).filter(
        NetworkScan.property_id == property_id if property_id else True,
    ).order_by(NetworkScan.scanned_at.desc()).first()
    
    if not latest_scan:
        return record_health(db, "monitoring", "NOT_CONFIGURED", organization_id=organization_id, property_id=property_id, details="No monitoring scans found")
    
    age = (datetime.now(timezone.utc) - latest_scan.scanned_at).total_seconds()
    if age > COMPONENT_FRESHNESS["monitoring"]:
        return record_health(db, "monitoring", "STALE", last_success=latest_scan.scanned_at, organization_id=organization_id, property_id=property_id, details=f"Last monitoring scan {age:.0f}s ago")
    
    return record_health(db, "monitoring", "HEALTHY", last_success=latest_scan.scanned_at, organization_id=organization_id, property_id=property_id)


def update_agent_health(db: Session, agent_id: str) -> SystemHealthSnapshot:
    """Update agent health based on heartbeat freshness."""
    agent = db.query(LocalAgentRegistration).filter_by(agent_id=agent_id).first()
    if not agent:
        return record_health(db, "agent", "FAILED", details=f"Agent {agent_id} not found")
    
    if agent.revoked_at or agent.retired_at:
        return record_health(db, "agent", "FAILED", organization_id=agent.organization_id, property_id=agent.property_id, details="Agent revoked or retired")
    
    if not agent.last_heartbeat:
        return record_health(db, "agent", "UNKNOWN", organization_id=agent.organization_id, property_id=agent.property_id, details="No heartbeat recorded")
    
    age = (datetime.now(timezone.utc) - agent.last_heartbeat).total_seconds()
    if age > COMPONENT_FRESHNESS["agent"]:
        status = "STALE" if age < 3600 else "FAILED"
        return record_health(db, "agent", status, last_success=agent.last_heartbeat, organization_id=agent.organization_id, property_id=agent.property_id, details=f"Last heartbeat {age:.0f}s ago")
    
    # Check queue health
    if agent.pending_queue > agent.queue_capacity * 0.8:
        return record_health(db, "agent", "DEGRADED", last_success=agent.last_heartbeat, organization_id=agent.organization_id, property_id=agent.property_id, details=f"Queue near capacity: {agent.pending_queue}/{agent.queue_capacity}")
    
    return record_health(db, "agent", "HEALTHY", last_success=agent.last_heartbeat, organization_id=agent.organization_id, property_id=agent.property_id)


def update_database_health(db: Session, is_available: bool, latency_ms: int | None = None) -> SystemHealthSnapshot:
    """Update database health based on connectivity check."""
    if not is_available:
        return record_health(db, "database", "FAILED", last_failure=datetime.now(timezone.utc), details="Database connectivity failed")
    
    details = f"Response time: {latency_ms}ms" if latency_ms else "Connected"
    return record_health(db, "database", "HEALTHY", last_success=datetime.now(timezone.utc), details=details)


def update_api_health(db: Session) -> SystemHealthSnapshot:
    """Update API health (called from health endpoint)."""
    return record_health(db, "api", "HEALTHY", last_success=datetime.now(timezone.utc), details="API responding")


def get_platform_health_summary(db: Session) -> dict:
    """Get platform-wide health summary for platform administrators."""
    components = ["api", "database", "scheduler", "discovery", "monitoring", "alert_processing", "notifications", "backup"]
    summary = {}
    
    for component in components:
        health = get_health(db, component)  # Platform-level (no org/property)
        if health:
            summary[component] = {
                "status": health.status,
                "last_success": health.last_success.isoformat() if health.last_success else None,
                "last_failure": health.last_failure.isoformat() if health.last_failure else None,
                "last_check": health.last_check.isoformat(),
                "details": health.details,
            }
        else:
            summary[component] = {"status": "UNKNOWN", "details": "No health data"}
    
    # Add backup-specific health
    from app.services.backup_service import get_backup_health
    backup_health = get_backup_health(db)
    summary["backup"] = backup_health
    
    # Agent summary
    total_agents = db.query(LocalAgentRegistration).filter(LocalAgentRegistration.revoked_at.is_(None)).count()
    healthy_agents = db.query(LocalAgentRegistration).filter(
        LocalAgentRegistration.revoked_at.is_(None),
        LocalAgentRegistration.last_heartbeat >= datetime.now(timezone.utc) - timedelta(seconds=COMPONENT_FRESHNESS["agent"]),
    ).count()
    
    summary["agents"] = {
        "total": total_agents,
        "healthy": healthy_agents,
        "status": "HEALTHY" if total_agents == healthy_agents else "DEGRADED" if healthy_agents > 0 else "FAILED",
    }
    
    return summary


def get_organization_health(db: Session, organization_id: UUID) -> dict:
    """Get organization-level health summary."""
    # Check for agents
    total_agents = db.query(LocalAgentRegistration).filter(
        LocalAgentRegistration.organization_id == organization_id,
        LocalAgentRegistration.revoked_at.is_(None),
    ).count()
    healthy_agents = db.query(LocalAgentRegistration).filter(
        LocalAgentRegistration.organization_id == organization_id,
        LocalAgentRegistration.revoked_at.is_(None),
        LocalAgentRegistration.last_heartbeat >= datetime.now(timezone.utc) - timedelta(seconds=COMPONENT_FRESHNESS["agent"]),
    ).count()
    
    # Get component health
    components = ["discovery", "monitoring", "agent"]
    component_health = {}
    
    for component in components:
        health = get_health(db, component, organization_id=organization_id)
        if health:
            component_health[component] = health.status
        else:
            component_health[component] = "UNKNOWN"
    
    # Determine overall status
    if any(s == "FAILED" for s in component_health.values()):
        overall = "FAILED"
    elif any(s in ("STALE", "DEGRADED") for s in component_health.values()):
        overall = "DEGRADED"
    elif all(s == "HEALTHY" for s in component_health.values()):
        overall = "HEALTHY"
    else:
        overall = "UNKNOWN"
    
    return {
        "overall": overall,
        "components": component_health,
        "agents": {"total": total_agents, "healthy": healthy_agents},
    }


def record_notification_delivery(
    db: Session,
    notification_type: str,
    recipient: str,
    status: str,
    error: str | None = None,
    organization_id: UUID | None = None,
) -> NotificationDelivery:
    """Record notification delivery attempt."""
    delivery = NotificationDelivery(
        notification_type=notification_type,
        recipient=recipient,
        status=status,
        error=error,
        organization_id=organization_id,
    )
    if status == "SENT":
        delivery.delivered_at = datetime.now(timezone.utc)
    db.add(delivery)
    db.commit()
    db.refresh(delivery)
    return delivery


def get_notification_health(db: Session, organization_id: UUID | None = None) -> dict:
    """Get notification delivery health."""
    recent = db.query(NotificationDelivery).filter(
        NotificationDelivery.organization_id == organization_id if organization_id else True,
        NotificationDelivery.attempted_at >= datetime.now(timezone.utc) - timedelta(hours=1),
    ).all()
    
    if not recent:
        return {"status": "NOT_CONFIGURED", "details": "No recent notifications"}
    
    failed = sum(1 for d in recent if d.status == "FAILED")
    pending = sum(1 for d in recent if d.status in ("PENDING", "RETRYING"))
    
    if failed > len(recent) * 0.5:
        return {"status": "FAILED", "details": f"{failed}/{len(recent)} recent deliveries failed"}
    if pending > 10:
        return {"status": "DEGRADED", "details": f"{pending} deliveries pending"}
    
    return {"status": "HEALTHY", "details": f"{len(recent)} recent deliveries, {failed} failed"}
