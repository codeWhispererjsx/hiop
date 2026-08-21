import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.access_control import OPERATIONAL_ROLES
from app.core.config import settings
from app.core.rate_limit import OperationRateLimiter
from app.core.security import get_current_user, get_db, hash_password, require_roles
from app.models.hierarchy import Property
from app.models.property_access import UserPropertyAccess
from app.models.saas_security import AccountToken, UserInvitation
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.billing_service import enforce_limit
from app.services.email_service import send_email

router = APIRouter(prefix="/accounts", tags=["Account security"])
admin = require_roles(["admin"])
public_limiter = OperationRateLimiter(limit=5, window_seconds=900)


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(admin|technician|viewer)$")
    property_id: str | None = None


class AcceptInvitation(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=12, max_length=128)


class EmailRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class PasswordResetRequest(TokenRequest):
    password: str = Field(min_length=12, max_length=128)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _validate_password(password: str) -> None:
    if not (re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"\d", password)):
        raise HTTPException(422, "Password must contain uppercase, lowercase, and a number")


def _url(path: str, token: str) -> str:
    origin = settings.cors_origins[0].rstrip("/") if settings.cors_origins else "http://localhost:5173"
    return f"{origin}{path}?token={token}"


def _safe_delivery(subject: str, body: str, recipient: str) -> str:
    result = send_email(subject, body, recipient, max_retries=1)
    return str(getattr(result.get("status"), "value", result.get("status")))


@router.post("/invitations", status_code=201)
def invite(payload: InviteRequest, db: Session = Depends(get_db), actor: User = Depends(admin)):
    enforce_limit(db, actor.organization_id, "users")
    email = str(payload.email).lower()
    if db.query(User).filter(func.lower(User.email) == email).first():
        raise HTTPException(409, "A user with this email already exists")
    property_row = db.get(Property, payload.property_id) if payload.property_id else None
    if property_row and property_row.organization_id != actor.organization_id:
        raise HTTPException(404, "Property not found")
    prior = db.query(UserInvitation).filter_by(organization_id=actor.organization_id, email=email, status="pending").first()
    if prior:
        prior.status = "replaced"
    raw = secrets.token_urlsafe(48)
    row = UserInvitation(organization_id=actor.organization_id, property_id=property_row.id if property_row else None, email=email, role=payload.role, token_hash=_hash(raw), invited_by=actor.id, expires_at=datetime.now(timezone.utc)+timedelta(hours=72))
    db.add(row); db.flush()
    delivery = _safe_delivery("You are invited to HIOP", f"Accept your secure invitation: {_url('/accept-invitation', raw)}\nThis link expires in 72 hours.", email)
    create_audit_log(db, actor.username, "USER_INVITED", "UserInvitation", str(row.id), f"Invited {email}", organization_id=actor.organization_id, property_id=row.property_id, event_category="security")
    db.commit()
    response = {"id": str(row.id), "email": email, "role": row.role, "status": row.status, "expires_at": row.expires_at, "delivery_status": delivery}
    if settings.environment == "testing": response["test_token"] = raw
    return response


@router.post("/invitations/accept", status_code=201)
def accept_invitation(payload: AcceptInvitation, request: Request, db: Session = Depends(get_db)):
    public_limiter.check(f"invite:{request.client.host if request.client else 'unknown'}")
    _validate_password(payload.password)
    now = datetime.now(timezone.utc)
    row = db.query(UserInvitation).filter_by(token_hash=_hash(payload.token), status="pending").first()
    if not row or row.expires_at <= now: raise HTTPException(400, "Invitation is invalid or expired")
    if db.query(User).filter(func.lower(User.username)==payload.username.lower()).first(): raise HTTPException(409, "Username already exists")
    user = User(username=payload.username, email=row.email, hashed_password=hash_password(payload.password), role=row.role, organization_id=row.organization_id, is_active=True, email_verified_at=now, invited_at=row.created_at, invitation_accepted_at=now)
    db.add(user); db.flush()
    if row.property_id: db.add(UserPropertyAccess(user_id=user.id, property_id=row.property_id, access_level=f"property_{'admin' if row.role=='admin' else row.role}", enabled=True, is_default=True, granted_by=row.invited_by))
    row.status="accepted"; row.accepted_by=user.id; row.accepted_at=now
    create_audit_log(db, user.username, "USER_INVITATION_ACCEPTED", "User", user.id, "Accepted secure invitation", organization_id=row.organization_id, property_id=row.property_id, event_category="security")
    db.commit(); return {"message":"Invitation accepted. You can now sign in."}


@router.post("/verification/request")
def request_verification(payload: EmailRequest, request: Request, db: Session = Depends(get_db)):
    public_limiter.check(f"verify:{request.client.host if request.client else 'unknown'}")
    user=db.query(User).filter(func.lower(User.email)==str(payload.email).lower()).first()
    response={"message":"If the account exists, verification instructions have been sent."}
    if not user or user.email_verified_at: return response
    raw=secrets.token_urlsafe(48); row=AccountToken(user_id=user.id,purpose="email_verification",token_hash=_hash(raw),expires_at=datetime.now(timezone.utc)+timedelta(hours=24),request_ip=request.client.host if request.client else None);db.add(row)
    _safe_delivery("Verify your HIOP email",f"Verify your email: {_url('/verify-email',raw)}",user.email);db.commit()
    if settings.environment=="testing":response["test_token"]=raw
    return response


@router.post("/verification/confirm")
def confirm_verification(payload: TokenRequest, db: Session = Depends(get_db)):
    now=datetime.now(timezone.utc);row=db.query(AccountToken).filter_by(token_hash=_hash(payload.token),purpose="email_verification",consumed_at=None).first()
    if not row or row.expires_at<=now:raise HTTPException(400,"Verification link is invalid or expired")
    user=db.get(User,row.user_id);user.email_verified_at=now;row.consumed_at=now;create_audit_log(db,user.username,"EMAIL_VERIFIED","User",user.id,"Verified account email",organization_id=user.organization_id,event_category="security");db.commit();return {"message":"Email verified."}


@router.post("/password-recovery/request")
def request_recovery(payload: EmailRequest, request: Request, db: Session = Depends(get_db)):
    public_limiter.check(f"recovery:{request.client.host if request.client else 'unknown'}");user=db.query(User).filter(func.lower(User.email)==str(payload.email).lower(),User.is_active.is_(True)).first();response={"message":"If the account exists, password reset instructions have been sent."}
    if not user:return response
    raw=secrets.token_urlsafe(48);row=AccountToken(user_id=user.id,purpose="password_reset",token_hash=_hash(raw),expires_at=datetime.now(timezone.utc)+timedelta(minutes=30),request_ip=request.client.host if request.client else None);db.add(row);_safe_delivery("Reset your HIOP password",f"Reset your password: {_url('/reset-password',raw)}\nThis link expires in 30 minutes.",user.email);db.commit()
    if settings.environment=="testing":response["test_token"]=raw
    return response


@router.post("/password-recovery/confirm")
def confirm_recovery(payload: PasswordResetRequest, db: Session = Depends(get_db)):
    _validate_password(payload.password)
    now=datetime.now(timezone.utc);row=db.query(AccountToken).filter_by(token_hash=_hash(payload.token),purpose="password_reset",consumed_at=None).first()
    if not row or row.expires_at<=now:raise HTTPException(400,"Password reset link is invalid or expired")
    user=db.get(User,row.user_id);user.hashed_password=hash_password(payload.password);user.must_change_password=False;user.tokens_valid_after=now;row.consumed_at=now;create_audit_log(db,user.username,"PASSWORD_RECOVERY_COMPLETED","User",user.id,"Password reset using a single-use link",organization_id=user.organization_id,event_category="security");db.commit();return {"message":"Password reset complete. Sign in again on all devices."}
