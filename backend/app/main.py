from fastapi import FastAPI

app = FastAPI(
    title="Hotel IT Operations Portal",
    version="1.0.0",
    description="Backend API for HIOP"
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