import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_db, hash_password
from app.models.hierarchy import Organization, Property
from app.models.property_access import UserPropertyAccess
from app.models.user import User
from app.services.audit_service import create_audit_log
from app.services.billing_service import start_trial

router = APIRouter(prefix="/public/onboarding", tags=["Public customer onboarding"])


class PublicOnboardingRequest(BaseModel):
    plan_code: str = Field(default="starter", pattern=r"^(starter|core|enterprise)$")
    organization_name: str = Field(min_length=2, max_length=160)
    organization_code: str = Field(min_length=2, max_length=40)
    contact_email: EmailStr
    country: str = Field(min_length=2, max_length=120)
    timezone: str = Field(min_length=3, max_length=64)
    phone: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=1000)
    property_name: str = Field(min_length=2, max_length=120)
    property_code: str = Field(min_length=2, max_length=40)
    property_city: str = Field(min_length=2, max_length=120)
    admin_username: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    admin_email: EmailStr
    admin_password: str = Field(min_length=12, max_length=128)

    @field_validator("admin_password")
    @classmethod
    def secure_password(cls, value: str) -> str:
        if not re.search(r"[A-Z]", value) or not re.search(r"[a-z]", value) or not re.search(r"\d", value):
            raise ValueError("Password must include uppercase, lowercase, and a number")
        return value


def normalized_code(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


@router.post("/register", status_code=201)
def register_customer(payload: PublicOnboardingRequest, db: Session = Depends(get_db)):
    organization_code = normalized_code(payload.organization_code)
    property_code = normalized_code(payload.property_code).upper()
    if len(organization_code) < 2 or len(property_code) < 2:
        raise HTTPException(422, "Enter a valid organization and property code")
    if db.query(Organization).filter(func.lower(Organization.code) == organization_code.lower()).first():
        raise HTTPException(409, "Organization code already exists")
    if db.query(Property).filter(func.lower(Property.code) == property_code.lower()).first():
        raise HTTPException(409, "Property code already exists")
    if db.query(User).filter(
        (func.lower(User.email) == str(payload.admin_email).lower())
        | (func.lower(User.username) == payload.admin_username.lower())
    ).first():
        raise HTTPException(409, "Administrator username or email already exists")

    try:
        organization = Organization(
            name=payload.organization_name.strip(), code=organization_code, country=payload.country.strip(),
            timezone=payload.timezone, status="active", contact_email=str(payload.contact_email).lower(),
            contact_phone=payload.phone, description=payload.description, hiop_version=settings.app_version,
            last_activity_at=datetime.now(timezone.utc),
        )
        db.add(organization)
        db.flush()
        administrator = User(
            username=payload.admin_username.strip(), email=str(payload.admin_email).lower(),
            hashed_password=hash_password(payload.admin_password), role="admin", is_active=True,
            organization_id=organization.id,
        )
        db.add(administrator)
        db.flush()
        property_row = Property(
            name=payload.property_name.strip(), code=property_code, organization_id=organization.id,
            city=payload.property_city.strip(), country=payload.country.strip(), timezone=payload.timezone,
            email=str(payload.contact_email).lower(), operational_status="active", is_active=True,
        )
        db.add(property_row)
        db.flush()
        organization.administrator_id = administrator.id
        organization.created_by = administrator.id
        db.add(UserPropertyAccess(
            user_id=administrator.id, property_id=property_row.id, access_level="property_admin",
            enabled=True, is_default=True, granted_by=administrator.id,
        ))
        create_audit_log(db, administrator.username, "CUSTOMER_ONBOARDING_COMPLETED", "Organization", str(organization.id), "Created organization and initial property through public onboarding")
        subscription = start_trial(db, organization.id, payload.plan_code, administrator)
        db.commit()
    except Exception:
        db.rollback()
        raise

    token = create_access_token({"sub": administrator.username})
    return {
        "access_token": token, "token_type": "bearer",
        "organization": {"id": str(organization.id), "name": organization.name, "code": organization.code},
        "property": {"id": str(property_row.id), "name": property_row.name, "code": property_row.code},
        "administrator": {"id": administrator.id, "username": administrator.username, "email": administrator.email, "role": "admin"},
        "subscription": {"id": str(subscription.id), "status": subscription.status, "plan_code": payload.plan_code},
    }
