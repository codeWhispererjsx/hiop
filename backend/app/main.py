from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from app.auth.routes import router as auth_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.database import SessionLocal
from app.models.network_scan import NetworkScan
from app.models.snmp import SNMPPollRun
from app.models.topology_operations import TopologyOperationalRun
from app.models.analytics import AnalyticsRun
from app.models.cmdb import CIHealthSnapshot
from app.devices.routes import router as device_router
from app.tickets.routes import router as ticket_router
from app.scanner.routes import router as scanner_router
from app.dashboard.routes import router as dashboard_router
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.services.scheduler_service import (
    start_scheduler,
    stop_scheduler,
)
from app.websocket.routes import router as websocket_router
from app.operations.routes import router as operations_router
from app.hierarchy.routes import router as hierarchy_router
from app.api.v1.hospitality import router as hospitality_router
from app.api.v1.physical import router as physical_router
from app.api.v1.context import router as context_router
from app.api.v1.operations import router as operations_v3_router
from app.api.v1.configuration_management import router as configuration_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.restore_workflow import router as restore_workflow_router
from app.api.v1.automation import router as automation_router
from app.api.v1.automation_triggers import router as automation_triggers_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.change_management import router as change_management_router
from app.api.v1.cmdb import router as cmdb_router
from app.api.v1.problem_management import router as problem_management_router
from app.api.v1.asset_management import router as asset_management_router
from app.api.v1.business_intelligence import router as business_intelligence_router
from app.api.v1.multi_property import router as multi_property_router
from app.discovery.routes import router as discovery_router
from app.imports.routes import router as imports_router
from app.users.routes import router as users_router
from app.audit.routes import router as audit_router
from app.reports.routes import router as reports_router
from app.services.scheduler_service import scheduler
from app.websocket.connection_manager import manager

configure_logging(settings.log_level)

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for the Hospitality IT Operations Platform (HIOP)",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.url.path.startswith(settings.api_prefix):
            response.headers["Cache-Control"] = "no-store"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(
    auth_router,
    prefix=settings.api_prefix
)

@app.get("/")
def root():
    return {
        "application": "Hospitality IT Operations Platform",
        "version": settings.app_version,
        "status": "running"
    }

@app.get("/health", tags=["Operations"])
def health():
    database = "available"
    last_scan = None
    snmp_health = {"integration_enabled": settings.snmp_enabled, "scheduler_jobs": 0, "active_polls": 0, "stale_runs": 0}
    topology_health = {"scheduler_jobs": 0, "active_runs": 0, "stale_runs": 0}
    analytics_health = {"integration_enabled": settings.analytics_enabled, "scheduler_jobs": 0, "active_runs": 0, "stale_runs": 0, "last_successful_run": None}
    cmdb_health = {"scheduler_jobs": 0, "latest_score": None, "last_calculated_at": None}
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        latest = db.query(NetworkScan.scanned_at).order_by(NetworkScan.scanned_at.desc()).first()
        last_scan = latest[0].isoformat() if latest and latest[0] else None
        if settings.snmp_enabled:
            cutoff = datetime.now(timezone.utc).timestamp() - settings.snmp_stale_run_timeout_seconds
            active = db.query(SNMPPollRun).filter(SNMPPollRun.status.in_(("pending", "running")))
            snmp_health["active_polls"] = active.count()
            snmp_health["stale_runs"] = sum(1 for run in active.limit(settings.snmp_poll_concurrency * 2).all() if run.started_at.timestamp() < cutoff)
            snmp_health["scheduler_jobs"] = sum(job.id.startswith("snmp_") for job in scheduler.get_jobs())
        topology_active = db.query(TopologyOperationalRun).filter(TopologyOperationalRun.status.in_(("pending", "running")))
        topology_health["active_runs"] = topology_active.count()
        topology_health["stale_runs"] = topology_active.filter(
            TopologyOperationalRun.started_at < datetime.now(timezone.utc) - timedelta(hours=1)
        ).count()
        topology_health["scheduler_jobs"] = sum(job.id.startswith("topology_") for job in scheduler.get_jobs())
        analytics_active = db.query(AnalyticsRun).filter(AnalyticsRun.status.in_(("pending", "running", "retry_pending")))
        analytics_health["active_runs"] = analytics_active.count()
        analytics_health["stale_runs"] = analytics_active.filter(
            AnalyticsRun.started_at < datetime.now(timezone.utc) - timedelta(hours=1)
        ).count()
        analytics_health["scheduler_jobs"] = sum(job.id.startswith("analytics_") for job in scheduler.get_jobs())
        analytics_latest = db.query(AnalyticsRun.completed_at).filter(
            AnalyticsRun.status == "completed"
        ).order_by(AnalyticsRun.completed_at.desc()).first()
        analytics_health["last_successful_run"] = analytics_latest[0].isoformat() if analytics_latest and analytics_latest[0] else None
        cmdb_health["scheduler_jobs"] = sum(job.id.startswith("cmdb_") for job in scheduler.get_jobs())
        cmdb_latest = db.query(CIHealthSnapshot).order_by(CIHealthSnapshot.calculated_at.desc()).first()
        if cmdb_latest:
            cmdb_health["latest_score"] = cmdb_latest.health_score
            cmdb_health["last_calculated_at"] = cmdb_latest.calculated_at.isoformat()
    except Exception:
        database = "unavailable"
    finally:
        db.close()

    scheduler_state = "disabled" if not settings.scheduler_enabled else "running" if scheduler.running else "stopped"
    healthy = database == "available" and scheduler_state in {"running", "disabled"}
    payload = {
        "status": "healthy" if healthy else "degraded",
        "api": "available",
        "database": database,
        "application_version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scheduler": scheduler_state,
        "websocket": {"status": "available", "active_connections": manager.connection_count},
        "network_scanner": "available",
        "last_scan": last_scan,
        "snmp": snmp_health,
        "topology": topology_health,
        "analytics": analytics_health,
        "cmdb": cmdb_health,
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)

app.include_router(
    device_router,
    prefix=settings.api_prefix
)

app.include_router(
    ticket_router,
    prefix=settings.api_prefix
)

app.include_router(
    scanner_router,
    prefix=settings.api_prefix
)

app.include_router(
    dashboard_router,
    prefix=settings.api_prefix
)

app.include_router(websocket_router)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(audit_router, prefix=settings.api_prefix)
app.include_router(reports_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)
app.include_router(hierarchy_router, prefix=settings.api_prefix)
app.include_router(hospitality_router, prefix=settings.api_prefix)
app.include_router(physical_router, prefix=settings.api_prefix)
app.include_router(context_router, prefix=settings.api_prefix)
app.include_router(operations_v3_router, prefix=settings.api_prefix)
app.include_router(configuration_router, prefix=settings.api_prefix)
app.include_router(compliance_router, prefix=settings.api_prefix)
app.include_router(restore_workflow_router, prefix=settings.api_prefix)
app.include_router(automation_router, prefix=settings.api_prefix)
app.include_router(automation_triggers_router, prefix=settings.api_prefix)
app.include_router(incidents_router, prefix=settings.api_prefix)
app.include_router(knowledge_router, prefix=settings.api_prefix)
app.include_router(change_management_router, prefix=settings.api_prefix)
app.include_router(cmdb_router, prefix=settings.api_prefix)
app.include_router(problem_management_router, prefix=settings.api_prefix)
app.include_router(asset_management_router, prefix=settings.api_prefix)
app.include_router(business_intelligence_router, prefix=settings.api_prefix)
app.include_router(multi_property_router, prefix=settings.api_prefix)
app.include_router(discovery_router, prefix=settings.api_prefix)
app.include_router(imports_router, prefix=settings.api_prefix)

from app.api.v1.active_directory import router as active_directory_router
app.include_router(active_directory_router, prefix=settings.api_prefix)
from app.api.v1.snmp import router as snmp_router
app.include_router(snmp_router, prefix=settings.api_prefix)
from app.api.v1.topology_operations import router as topology_operations_router
app.include_router(topology_operations_router, prefix=settings.api_prefix)
from app.api.v1.topology import router as topology_router
app.include_router(topology_router, prefix=settings.api_prefix)
from app.api.v1.analytics import router as analytics_router
app.include_router(analytics_router, prefix=settings.api_prefix)
