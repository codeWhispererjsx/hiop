from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.models.system_health import HealthEvent, JobExecution, SystemHealthSnapshot
from app.services.health_service import (
    COMPONENT_FRESHNESS,
    check_job_staleness,
    get_health,
    get_notification_health,
    get_organization_health,
    get_platform_health_summary,
    record_health,
    record_job_execution,
    update_agent_health,
    update_discovery_health,
    update_monitoring_health,
    update_scheduler_health,
)
from app.models.user import User

router = APIRouter(prefix="/system-health", tags=["System Health"])
platform_admin = require_roles(["platformadmin"])
org_admin = require_roles(["platformadmin", "admin"])

HealthStatus = Literal["HEALTHY", "DEGRADED", "STALE", "FAILED", "NOT_CONFIGURED", "UNKNOWN"]


class ComponentHealth(BaseModel):
    component: str
    status: HealthStatus
    last_success: str | None
    last_failure: str | None
    last_check: str
    details: str | None


class PlatformHealthSummary(BaseModel):
    api: ComponentHealth
    database: ComponentHealth
    scheduler: ComponentHealth
    discovery: ComponentHealth
    monitoring: ComponentHealth
    alert_processing: ComponentHealth
    notifications: ComponentHealth
    agents: dict


class OrganizationHealthSummary(BaseModel):
    overall: HealthStatus
    components: dict[str, HealthStatus]
    agents: dict


class JobExecutionModel(BaseModel):
    id: str
    job_id: str
    job_type: str
    status: str
    started_at: str
    completed_at: str | None
    duration_seconds: int | None
    error: str | None
    result_summary: str | None
    correlation_id: str | None


class HealthEventModel(BaseModel):
    id: str
    component: str
    previous_status: str | None
    new_status: str
    reason: str | None
    created_at: str


@router.get("/platform", response_model=PlatformHealthSummary)
def get_platform_health(db: Session = Depends(get_db), _: User = Depends(platform_admin)):
    """Get platform-wide health summary for platform administrators."""
    summary = get_platform_health_summary(db)
    
    # Convert to response model
    components = {}
    for component, data in summary.items():
        if component == "agents":
            continue
        components[component] = ComponentHealth(
            component=component,
            status=data.get("status", "UNKNOWN"),
            last_success=data.get("last_success"),
            last_failure=data.get("last_failure"),
            last_check=data.get("last_check", datetime.now(timezone.utc).isoformat()),
            details=data.get("details"),
        )
    
    return PlatformHealthSummary(
        **components,
        agents=summary.get("agents", {"total": 0, "healthy": 0, "status": "UNKNOWN"}),
    )


@router.get("/organizations/{organization_id}", response_model=OrganizationHealthSummary)
def get_org_health(
    organization_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(org_admin),
    org=Depends(organization_context),
):
    """Get organization-level health summary."""
    if str(organization_id) != str(org):
        raise HTTPException(403, "Cannot access another organization's health")
    
    summary = get_organization_health(db, organization_id)
    return OrganizationHealthSummary(**summary)


@router.get("/components/{component}")
def get_component_health(
    component: str,
    organization_id: UUID | None = Query(None),
    property_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(org_admin),
    org=Depends(organization_context),
):
    """Get health details for a specific component."""
    # Enforce scope
    if organization_id and str(organization_id) != str(org):
        raise HTTPException(403, "Cannot access another organization's health")
    
    health = get_health(db, component, organization_id, property_id)
    if not health:
        raise HTTPException(404, "Component health not found")
    
    return {
        "component": health.component,
        "status": health.status,
        "last_success": health.last_success.isoformat() if health.last_success else None,
        "last_failure": health.last_failure.isoformat() if health.last_failure else None,
        "last_check": health.last_check.isoformat(),
        "details": health.details,
        "organization_id": str(health.organization_id) if health.organization_id else None,
        "property_id": str(health.property_id) if health.property_id else None,
    }


@router.get("/components/{component}/history")
def get_component_history(
    component: str,
    limit: int = Query(50, ge=1, le=500),
    organization_id: UUID | None = Query(None),
    property_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(org_admin),
    org=Depends(organization_context),
):
    """Get health event history for a component."""
    # Enforce scope
    if organization_id and str(organization_id) != str(org):
        raise HTTPException(403, "Cannot access another organization's health")
    
    events = db.query(HealthEvent).filter(
        HealthEvent.component == component,
        HealthEvent.organization_id == organization_id if organization_id else True,
        HealthEvent.property_id == property_id if property_id else True,
    ).order_by(HealthEvent.created_at.desc()).limit(limit).all()
    
    return [
        HealthEventModel(
            id=str(event.id),
            component=event.component,
            previous_status=event.previous_status,
            new_status=event.new_status,
            reason=event.reason,
            created_at=event.created_at.isoformat(),
        )
        for event in events
    ]


@router.get("/jobs/{job_type}/executions")
def get_job_executions(
    job_type: str,
    limit: int = Query(50, ge=1, le=500),
    organization_id: UUID | None = Query(None),
    property_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(org_admin),
    org=Depends(organization_context),
):
    """Get execution history for a job type."""
    # Enforce scope
    if organization_id and str(organization_id) != str(org):
        raise HTTPException(403, "Cannot access another organization's job history")
    
    executions = db.query(JobExecution).filter(
        JobExecution.job_type == job_type,
        JobExecution.organization_id == organization_id if organization_id else True,
        JobExecution.property_id == property_id if property_id else True,
    ).order_by(JobExecution.started_at.desc()).limit(limit).all()
    
    return [
        JobExecutionModel(
            id=str(execution.id),
            job_id=execution.job_id,
            job_type=execution.job_type,
            status=execution.status,
            started_at=execution.started_at.isoformat(),
            completed_at=execution.completed_at.isoformat() if execution.completed_at else None,
            duration_seconds=execution.duration_seconds,
            error=execution.error,
            result_summary=execution.result_summary,
            correlation_id=execution.correlation_id,
        )
        for execution in executions
    ]


@router.get("/notifications/health")
def get_notifications_health(
    organization_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(org_admin),
    org=Depends(organization_context),
):
    """Get notification delivery health."""
    # Enforce scope
    if organization_id and str(organization_id) != str(org):
        raise HTTPException(403, "Cannot access another organization's notification health")
    
    return get_notification_health(db, organization_id)


@router.post("/components/{component}/refresh")
def refresh_component_health(
    component: str,
    organization_id: UUID | None = Query(None),
    property_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(org_admin),
    org=Depends(organization_context),
):
    """Manually trigger health refresh for a component."""
    # Enforce scope
    if organization_id and str(organization_id) != str(org):
        raise HTTPException(403, "Cannot refresh another organization's health")
    
    from app.services.scheduler_service import scheduler
    
    if component == "scheduler":
        return update_scheduler_health(db, scheduler.running)
    elif component == "discovery":
        return update_discovery_health(db, organization_id, property_id)
    elif component == "monitoring":
        return update_monitoring_health(db, organization_id, property_id)
    else:
        raise HTTPException(400, f"Manual refresh not supported for component: {component}")
