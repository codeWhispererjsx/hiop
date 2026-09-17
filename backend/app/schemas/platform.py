from typing import Literal
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2,max_length=160)
    code: str | None = Field(default=None,max_length=40)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None,max_length=40)
    notes: str | None = Field(default=None,max_length=2000)

class OrganizationUpdate(BaseModel):
    billing_exempt: bool | None = None
    access_override: Literal["subscription", "keep_active", "suspended"] | None = None
    name: str | None = Field(default=None,min_length=2,max_length=160)
    contact_email: EmailStr | None = None
    contact_phone: str | None = Field(default=None,max_length=40)
    notes: str | None = Field(default=None,max_length=2000)

class OrganizationAdminCreate(BaseModel):
    username: str = Field(min_length=3,max_length=50)
    email: EmailStr
    password: str = Field(min_length=10,max_length=128)

class PlatformAdminCreate(BaseModel):
    username: str = Field(min_length=3,max_length=50)
    email: EmailStr
    password: str = Field(min_length=10,max_length=128)

class PlatformBootstrapCreate(BaseModel):
    username: str = Field(min_length=3,max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    email: EmailStr
    password: str = Field(min_length=12,max_length=128)

class OrganizationRead(BaseModel):
    id: UUID; name: str; code: str; status: str; contact_email: str | None=None; contact_phone: str | None=None; notes: str | None=None
    administrator_id: str | None=None; hiop_version: str; created_at: datetime; updated_at: datetime; last_activity_at: datetime | None=None
    users: int=0; assets: int=0; devices: int=0; active_alerts: int=0; open_incidents: int=0
