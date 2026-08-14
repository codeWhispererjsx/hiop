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
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.services.scheduler_service import (
    start_scheduler,
    stop_scheduler,
)
from app.websocket.routes import router as websocket_router
from app.operations.routes import router as operations_router
from app.hierarchy.routes import router as hierarchy_router
from app.api.v1.automation import router as automation_router
from app.api.v1.automation_triggers import router as automation_triggers_router
from app.api.v1.incidents import router as incidents_router
from app.api.v1.discovery_intelligence import router as discovery_intelligence_router
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
from app.users.routes import router as users_router
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
    allow_headers=["Authorization", "Content-Type", "X-Organization-ID"],
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
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        latest = db.query(NetworkScan.scanned_at).order_by(NetworkScan.scanned_at.desc()).first()
        last_scan = latest[0].isoformat() if latest and latest[0] else None
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
    }
    return JSONResponse(payload, status_code=200 if healthy else 503)

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

app.include_router(websocket_router)
app.include_router(users_router, prefix=settings.api_prefix)
app.include_router(operations_router, prefix=settings.api_prefix)
app.include_router(hierarchy_router, prefix=settings.api_prefix)
app.include_router(automation_router, prefix=settings.api_prefix)
app.include_router(automation_triggers_router, prefix=settings.api_prefix)
app.include_router(incidents_router, prefix=settings.api_prefix)
app.include_router(discovery_intelligence_router, prefix=settings.api_prefix)
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
