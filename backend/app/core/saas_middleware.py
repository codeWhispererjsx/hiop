import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.core.rate_limit import api_request_limiter
from app.core.security import decode_access_token
from app.db.database import SessionLocal
from app.models.hierarchy import Organization, Property
from app.models.property_access import UserPropertyAccess
from app.models.saas_security import SecurityAccessEvent
from app.models.user import User
from app.core.config import settings
from app.services.billing_service import require_entitlement

ENTITLEMENTS = {
    "/api/v1/reporting": "reporting_basic", "/api/v1/topology": "topology",
    "/api/v1/problems": "problem_management", "/api/v1/changes": "change_management",
    "/api/v1/procurement": "procurement", "/api/v1/vendors": "vendors",
    "/api/v1/knowledge": "knowledge", "/api/v1/local-agents": "discovery",
}


class SaaSSecurityMiddleware(BaseHTTPMiddleware):
    """Central authenticated request guard and organization/property access log."""

    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/api/v1"):
            return await call_next(request)
        started = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        client_ip = request.client.host if request.client else "unknown"
        try:
            api_request_limiter.check(f"{client_ip}:{request.url.path.split('/')[3] if len(request.url.path.split('/')) > 3 else 'api'}")
        except Exception as exc:
            response = JSONResponse({"detail": getattr(exc, "detail", "Too many requests")}, status_code=429, headers={"Retry-After": getattr(exc, "headers", {}).get("Retry-After", "60")})
            self._record(request, response.status_code, request_id, started, client_ip, denied=True)
            return response

        auth = request.headers.get("Authorization", "")
        payload = decode_access_token(auth[7:]) if auth.startswith("Bearer ") else None
        denied = False
        user = None
        db = SessionLocal()
        try:
            if payload:
                user = db.query(User).filter(User.email == payload.get("sub"), User.is_active.is_(True)).first()
                if not user:
                    denied = True
                    response = JSONResponse({"detail":"Could not validate credentials"}, status_code=401)
                    return response
                organization = db.get(Organization, user.organization_id) if user.organization_id else None
                if organization and organization.offboarding_status in {"suspended", "erasure_scheduled", "erased"}:
                    denied=True;response=JSONResponse({"detail":"Organization access is suspended"},status_code=403);return response
                if settings.commercial_enforcement_enabled and user.role != "platformadmin" and user.organization_id:
                    entitlement=next((value for prefix,value in ENTITLEMENTS.items() if request.url.path.startswith(prefix)),None)
                    if entitlement:
                        try:require_entitlement(db,user.organization_id,entitlement)
                        except Exception as exc:
                            denied=True;response=JSONResponse({"detail":getattr(exc,"detail","Plan entitlement required")},status_code=getattr(exc,"status_code",403));return response
                requested_org = request.headers.get("X-HIOP-Organization-ID") or request.headers.get("X-Organization-ID")
                if user.role != "platformadmin" and requested_org and str(user.organization_id) != requested_org:
                    denied=True;response=JSONResponse({"detail":"Organization access denied"},status_code=403);return response
                requested_property = request.headers.get("X-HIOP-Property-ID")
                if requested_property and user.role != "platformadmin":
                    prop = db.get(Property, requested_property)
                    allowed = bool(prop and prop.organization_id == user.organization_id)
                    if allowed and user.role != "admin":
                        allowed = db.query(UserPropertyAccess).filter_by(user_id=user.id, property_id=prop.id, enabled=True).first() is not None
                    if not allowed:
                        denied=True;response=JSONResponse({"detail":"Property access denied"},status_code=403);return response
            response = await call_next(request)
            denied = response.status_code in {401,403}
            return response
        finally:
            status_code = response.status_code if "response" in locals() else 500
            try:
                event = SecurityAccessEvent(request_id=request_id, actor_user_id=user.id if user else None, organization_id=user.organization_id if user else None, property_id=request.headers.get("X-HIOP-Property-ID") or None, method=request.method, path=request.url.path[:500], status_code=status_code, source_ip=client_ip, user_agent=request.headers.get("User-Agent", "")[:500], denied=denied, duration_ms=max(0,int((time.perf_counter()-started)*1000)))
                db.add(event);db.commit()
            except Exception:
                db.rollback()
            finally:
                db.close()
            if "response" in locals(): response.headers["X-Request-ID"] = request_id

    @staticmethod
    def _record(request, status_code, request_id, started, client_ip, denied):
        db=SessionLocal()
        try:
            db.add(SecurityAccessEvent(request_id=request_id,method=request.method,path=request.url.path[:500],status_code=status_code,source_ip=client_ip,user_agent=request.headers.get("User-Agent","")[:500],denied=denied,duration_ms=max(0,int((time.perf_counter()-started)*1000))));db.commit()
        except Exception:db.rollback()
        finally:db.close()
