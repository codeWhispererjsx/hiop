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
from app.devices.routes import router as device_router
from app.scanner.routes import router as scanner_router
from app.dashboard.routes import router as dashboard_router
from app.discovery.routes import router as discovery_router
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.services.scheduler_service import (
    start_scheduler,
    stop_scheduler,
)
from app.services.health_service import (
    get_platform_health_summary,
    record_health,
    update_database_health,
    update_api_health,
)
from app.websocket.routes import router as websocket_router
from app.operations.routes import router as operations_router
from app.hierarchy.routes import router as hierarchy_router
from app.api.v1.automation import router as automation_router
from app.api.v1.automation_triggers import router as automation_triggers_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.discovery_intelligence import router as discovery_intelligence_router
from app.api.v1.snmp import router as snmp_router
from app.api.v1.active_directory_v2c import router as active_directory_v2c_router
from app.api.v1.topology_v3a import router as topology_v3a_router
from app.api.v1.port_intelligence import router as port_intelligence_router
from app.api.v1.segmentation import router as segmentation_router
from app.api.v1.monitoring_health import router as monitoring_health_router
from app.api.v1.alerts_events import router as alerts_events_router
from app.api.v1.assets import router as assets_router
from app.api.v1.platform import router as platform_router
from app.api.v1.procurement import router as procurement_router
from app.api.v1.vendors import router as vendors_router
from app.api.v1.service_management import router as service_management_router
from app.api.v1.organization_structure import router as organization_structure_router
from app.api.v1.problems import router as problems_router
from app.api.v1.changes import router as changes_router
from app.api.v1.knowledge_base import router as knowledge_base_router
from app.api.v1.reporting import router as reporting_router
from app.api.v1.property_management import router as property_management_router
from app.api.v1.public_onboarding import router as public_onboarding_router
from app.api.v1.billing import router as billing_router
from app.api.v1.onboarding_progress import router as onboarding_progress_router
from app.api.v1.local_agents import admin_router as local_agent_admin_router, agent_router as local_agent_router
from app.api.v1.system_health import router as system_health_router
from app.api.v1.backup_recovery import router as backup_recovery_router
from app.api.v1.email import router as email_router
from app.api.v1.circuit_breakers import router as circuit_breakers_router
from app.api.v1.integration_status import router as integration_status_router
from app.users.routes import router as users_router
from app.services.scheduler_service import scheduler
from app.websocket.connection_manager import manager
from app.core.tenant_middleware import TenantMiddleware

configure_logging(settings.log_level)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.services.integration_status import initialize_integrations
    initialize_integrations()
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
    allow_headers=["Authorization", "Content-Type", "X-Organization-ID", "X-HIOP-Organization-ID", "X-HIOP-Property-ID"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        if request.url.path.startswith(settings.api_prefix):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
        return response


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(TenantMiddleware)

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
    db = SessionLocal()
    try:
        # Check database with timing
        import time
        start = time.perf_counter()
        db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        database_available = True
    except Exception:
        database_available = False
        latency_ms = None
    finally:
        db.close()
    
    # Update health records (gracefully handle if tables don't exist)
    db = SessionLocal()
    try:
        if database_available:
            update_database_health(db, database_available, latency_ms)
        else:
            update_database_health(db, database_available, latency_ms)
        update_api_health(db)
        
        # Get last scan info
        last_scan = None
        if database_available:
            latest = db.query(NetworkScan.scanned_at).order_by(NetworkScan.scanned_at.desc()).first()
            last_scan = latest[0].isoformat() if latest and latest[0] else None
    except Exception as e:
        # Health tables may not exist, log and continue
        pass
    finally:
        db.close()

    scheduler_state = "disabled" if not settings.scheduler_enabled else "running" if scheduler.running else "stopped"
    healthy = database_available and scheduler_state in {"running", "disabled"}
    payload = {
        "status": "healthy" if healthy else "degraded",
        "api": "available",
        "database": "available" if database_available else "unavailable",
        "database_latency_ms": latency_ms,
        "application_version": settings.app_version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scheduler": scheduler_state,
        "websocket": {"status": "available", "active_connections": manager.connection_count},
        "network_scanner": "configured",
        "last_scan": last_scan,
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)


@app.get("/healthz", tags=["Operations"])
def healthz():
    """Baseline readiness: API process, database connectivity, and scheduler state."""
    database = "available"
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "unavailable"
    finally:
        db.close()
    scheduler_state = "disabled" if not settings.scheduler_enabled else "running" if scheduler.running else "stopped"
    healthy = database == "available" and scheduler_state in {"running", "disabled"}
    return JSONResponse({"status": "healthy" if healthy else "degraded", "api": "available", "database": database, "scheduler": scheduler_state}, status_code=200 if healthy else 503)

app.include_router(
    device_router,
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

app.include_router(
    discovery_router,
    prefix=settings.api_prefix
)

app.include_router(websocket_router)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)
app.include_router(hierarchy_router, prefix=settings.api_prefix)
app.include_router(automation_router, prefix=settings.api_prefix)
app.include_router(automation_triggers_router, prefix=settings.api_prefix)
app.include_router(incidents_router, prefix=settings.api_prefix)
app.include_router(discovery_intelligence_router, prefix=settings.api_prefix)
app.include_router(snmp_router, prefix=settings.api_prefix)
app.include_router(active_directory_v2c_router, prefix=settings.api_prefix)
app.include_router(topology_v3a_router, prefix=settings.api_prefix)
app.include_router(port_intelligence_router, prefix=settings.api_prefix)
app.include_router(segmentation_router, prefix=settings.api_prefix)
app.include_router(monitoring_health_router, prefix=settings.api_prefix)
app.include_router(alerts_events_router, prefix=settings.api_prefix)
app.include_router(assets_router, prefix=settings.api_prefix)
app.include_router(platform_router, prefix=settings.api_prefix)
app.include_router(procurement_router, prefix=settings.api_prefix)
app.include_router(vendors_router, prefix=settings.api_prefix)
app.include_router(service_management_router, prefix=settings.api_prefix)
app.include_router(organization_structure_router, prefix=settings.api_prefix)
app.include_router(problems_router, prefix=settings.api_prefix)
app.include_router(changes_router, prefix=settings.api_prefix)
app.include_router(knowledge_base_router, prefix=settings.api_prefix)
app.include_router(reporting_router, prefix=settings.api_prefix)
app.include_router(property_management_router, prefix=settings.api_prefix)
app.include_router(public_onboarding_router, prefix=settings.api_prefix)
app.include_router(billing_router, prefix=settings.api_prefix)
app.include_router(onboarding_progress_router, prefix=settings.api_prefix)
app.include_router(local_agent_admin_router, prefix=settings.api_prefix)
app.include_router(local_agent_router, prefix=settings.api_prefix)
app.include_router(system_health_router, prefix=settings.api_prefix)
app.include_router(backup_recovery_router, prefix=settings.api_prefix)
app.include_router(email_router, prefix=settings.api_prefix)
app.include_router(circuit_breakers_router, prefix=settings.api_prefix)
app.include_router(integration_status_router, prefix=settings.api_prefix)
