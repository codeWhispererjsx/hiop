from datetime import datetime, timezone

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
    description="Backend API for HIOP",
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
        "application": "Hotel IT Operations Portal",
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
app.include_router(discovery_router, prefix=settings.api_prefix)
app.include_router(imports_router, prefix=settings.api_prefix)
