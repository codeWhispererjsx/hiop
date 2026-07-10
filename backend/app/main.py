from fastapi import FastAPI
from app.auth.routes import router as auth_router
from app.core.config import settings
from app.devices.routes import router as device_router
from app.tickets.routes import router as ticket_router
from app.scanner.routes import router as scanner_router

app = FastAPI(
    title="Hotel IT Operations Portal",
    version="1.0.0",
    description="Backend API for HIOP"
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