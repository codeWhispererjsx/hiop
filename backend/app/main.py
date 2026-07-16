from fastapi import FastAPI
from app.auth.routes import router as auth_router
from app.core.config import settings
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
from app.users.routes import router as users_router
from app.audit.routes import router as audit_router
from app.reports.routes import router as reports_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()

    yield

    stop_scheduler()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend API for HIOP",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(
    auth_router,
    prefix=settings.api_prefix
)

@app.get("/")
def root():
    return {
        "application": "Hotel IT Operations Portal",
        "version": "1.0.0",
        "status": "running"
    }

@app.get("/health")
def health():
    return {
        "status": "healthy"
    }

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
