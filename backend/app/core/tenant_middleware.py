import logging
from typing import Optional
from fastapi import Request, HTTPException, status
from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.hierarchy import Organization
from app.core.config import settings

tenant_logger = logging.getLogger("hiop.tenant")


class TenantMiddleware:
    """Middleware to extract tenant context from subdomain and validate access."""
    
    def __init__(self, app):
        self.app = app
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
    
    async def __call__(self, request: Request, call_next):
        """Process request to extract and validate tenant context."""
        
        # Skip tenant validation for public routes and health checks
        if self._is_public_route(request.url.path):
            return await call_next(request)
        
        # Only process subdomain routing if enabled
        if not self.enable_routing:
            return await call_next(request)
        
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
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Organization not found"
                )
        else:
            # No subdomain - this might be direct access to main domain
            # For now, allow this for development compatibility
            tenant_logger.debug(f"No tenant subdomain found in host: {host}")
        
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
            "/public/onboarding",
            "/auth/login",
            "/api/v1/billing/public"
        ]
        return any(path.startswith(public_path) for public_path in public_paths)
    
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