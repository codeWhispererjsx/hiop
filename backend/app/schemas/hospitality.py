from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

OrganizationType = Literal["hospitality_group", "operator", "brand", "owner"]
PropertyType = Literal["hotel", "resort", "apartment", "conference_center", "restaurant", "mixed_hospitality"]
OperationalStatus = Literal["active", "inactive", "maintenance", "archived"]


class OrganizationWrite(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    type: OrganizationType = "hospitality_group"
    country: str | None = Field(default=None, max_length=120)
    timezone: str = Field(default="UTC", max_length=64)
    logo: str | None = Field(default=None, max_length=500)
    status: OperationalStatus = "active"

    @field_validator("name", "code", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class OrganizationRead(OrganizationWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class PropertyWrite(BaseModel):
    organization_id: UUID | None = None
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    type: PropertyType = "hotel"
    address: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=255)
    timezone: str = Field(default="UTC", max_length=64)
    number_of_rooms: int | None = Field(default=None, ge=0, le=2_000_000)
    number_of_floors: int | None = Field(default=None, ge=0, le=10_000)
    operational_status: OperationalStatus = "active"

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class PropertyRead(PropertyWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class Page(BaseModel):
    items: list
    total: int
    page: int
    page_size: int
