from fastapi import FastAPI
from app.auth.routes import router as auth_router
from app.core.config import settings

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