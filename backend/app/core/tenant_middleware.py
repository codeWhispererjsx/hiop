import logging
from typing import Optional
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.hierarchy import Organization
from app.core.config import settings
from starlette.middleware.base import BaseHTTPMiddleware

tenant_logger = logging.getLogger("hiop.tenant")


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to extract tenant context from subdomain and validate access."""
    
    def __init__(self, app):
        super().__init__(app)
        # Base domain for tenant subdomain extraction
        self.base_domain = settings.base_domain
        self.enable_routing = settings.enable_subdomain_routing
    
    def _get_base_domain(self) -> str:
        """Extract base domain from CORS origins or use default."""
        if settings.cors_origins:
            # Extract domain from first CORS origin
            origin = settings.cors_origins[0]
            if origin.startswith("http://"):
                origin = origin[7:]
            elif origin.startswith("https://"):
                origin = origin[8:]
            # Remove port if present
            if ":" in origin:
                origin = origin.split(":")[0]
            return origin
        return "localhost"  # Default for development
    
    async def dispatch(self, request: Request, call_next):
        """Process request to extract and validate tenant context."""
        from starlette.responses import JSONResponse
        
        # Check for path-based tenant routing
        path = request.url.path
        tenant_code = None
        
        # Path format: /t/{tenant_code}/...
        if path.startswith("/t/"):
            parts = path.split("/", 3)
            if len(parts) >= 3:
                tenant_code = parts[2].lower().strip()
                # Rewrite the path in the ASGI scope so FastAPI routes match correctly
                new_path = "/" + parts[3] if len(parts) > 3 else "/"
                request.scope["path"] = new_path
        
        # Skip tenant validation for public routes and health checks
        check_path = request.scope.get("path", request.url.path)
        if self._is_public_route(check_path):
            return await call_next(request)
        
        # Only process routing if enabled
        if not self.enable_routing:
            return await call_next(request)
        
        if not tenant_code:
            # Extract subdomain from Host header
            host = request.headers.get("host", "")
            tenant_code = self._extract_tenant_code(host)
        
        if tenant_code:
            # Look up organization by tenant code
            organization = self._get_organization_by_code(tenant_code)
            if organization:
                # Store tenant context in request state
                request.state.tenant_id = str(organization.id)
                request.state.tenant_code = organization.code
                request.state.organization = organization
                tenant_logger.info(f"Tenant context set: {tenant_code} -> {organization.id}")
            else:
                tenant_logger.warning(f"Invalid tenant code: {tenant_code}")
                return JSONResponse(
                    status_code=404,
                    content={"detail": "Organization not found"}
                )
        else:
            # No subdomain or path prefix - this might be direct access to main domain
            # For now, allow this for development compatibility
            tenant_logger.debug("No tenant context found in request")
        
        response = await call_next(request)
        return response
    
    def _is_public_route(self, path: str) -> bool:
        """Check if the route is public and doesn't require tenant validation."""
        public_paths = [
            "/health",
            "/healthz",
            "/",
            "/docs",
            "/openapi.json",
            # Auth and public routes (with and without API prefix)
            "/auth/",
            "/api/v1/auth/",
            "/public/onboarding",
            "/api/v1/public/onboarding",
            "/api/v1/billing/public",
            "/billing/public",
            "/api/v1/onboarding/",
            "/onboarding/",
        ]
        # Exact match for root
        if path == "/":
            return True
        return any(path.startswith(pp) for pp in public_paths if pp != "/")
    
    def _extract_tenant_code(self, host: str) -> Optional[str]:
        """Extract tenant code from subdomain."""
        if not host:
            return None
        
        # Remove port if present
        if ":" in host:
            host = host.split(":")[0]
        
        # If host matches base domain exactly, no subdomain
        if host == self.base_domain:
            return None
        
        # Extract subdomain
        if host.endswith(f".{self.base_domain}"):
            subdomain = host[:-len(f".{self.base_domain}")]
            return subdomain.lower().strip()
        
        # For development with localhost
        if host.startswith("localhost") or host.startswith("127.0.0.1"):
            return None
        
        return None
    
    def _get_organization_by_code(self, code: str) -> Optional[Organization]:
        """Look up organization by code."""
        try:
            db: Session = SessionLocal()
            try:
                organization = db.query(Organization).filter(
                    Organization.code == code,
                    Organization.status == "active"
                ).first()
                return organization
            finally:
                db.close()
        except Exception as e:
            tenant_logger.error(f"Error looking up organization {code}: {e}")
            return None


def get_tenant_id(request: Request) -> Optional[str]:
    """Get tenant ID from request state."""
    return getattr(request.state, "tenant_id", None)


def get_tenant_code(request: Request) -> Optional[str]:
    """Get tenant code from request state."""
    return getattr(request.state, "tenant_code", None)


def get_organization(request: Request) -> Optional[Organization]:
    """Get organization from request state."""
    org = getattr(request.state, "organization", None)
    # Return None instead of Organization object to avoid attribute errors
    return org