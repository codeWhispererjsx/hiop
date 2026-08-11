from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

STATUSES = {"planned", "received", "deployed", "active", "in_maintenance", "retired"}
CONDITIONS = {"new", "good", "fair", "poor", "damaged"}
CATEGORIES = {"device", "network", "server", "application", "service", "other"}


class AssetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    device_type: str = Field(min_length=1, max_length=80)
    status: str = "active"
    asset_tag: str | None = Field(default=None, max_length=80)
    ci_category: str = "device"
    vendor: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=160)
    serial_number: str | None = Field(default=None, max_length=180)
    department_id: UUID | None = None
    department_name: str | None = Field(default=None, max_length=120)
    room_id: UUID | None = None
    location_name: str | None = Field(default=None, max_length=160)
    business_owner: str | None = Field(default=None, max_length=180)
    technical_owner: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    condition: str | None = None
    acquisition_date: date | None = None
    received_date: date | None = None
    deployment_date: date | None = None
    warranty_start: date | None = None
    warranty_end: date | None = None
    expected_replacement_date: date | None = None
    lifecycle_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("name", "device_type")
    @classmethod
    def required_text(cls, value: str):
        value = value.strip()
        if not value: raise ValueError("Value cannot be blank")
        return value

    @field_validator("asset_tag", "vendor", "model", "serial_number", "department_name", "location_name", "business_owner", "technical_owner", "description")
    @classmethod
    def optional_text(cls, value: str | None):
        return value.strip() or None if value is not None else None

    @field_validator("status")
    @classmethod
    def status_value(cls, value: str):
        if value not in STATUSES: raise ValueError("Unsupported asset status")
        return value

    @field_validator("ci_category")
    @classmethod
    def category_value(cls, value: str):
        if value not in CATEGORIES: raise ValueError("Unsupported CI category")
        return value

    @field_validator("condition")
    @classmethod
    def condition_value(cls, value: str | None):
        if value is not None and value not in CONDITIONS: raise ValueError("Unsupported asset condition")
        return value


class AssetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    asset_tag: str | None = Field(default=None, max_length=80)
    device_type: str | None = Field(default=None, min_length=1, max_length=80)
    status: str | None = None
    ci_category: str | None = None
    vendor: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=160)
    serial_number: str | None = Field(default=None, max_length=180)
    department_id: UUID | None = None
    department_name: str | None = Field(default=None, max_length=120)
    room_id: UUID | None = None
    location_name: str | None = Field(default=None, max_length=160)
    business_owner: str | None = Field(default=None, max_length=180)
    technical_owner: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=2000)
    condition: str | None = None
    acquisition_date: date | None = None
    received_date: date | None = None
    deployment_date: date | None = None
    warranty_start: date | None = None
    warranty_end: date | None = None
    expected_replacement_date: date | None = None
    lifecycle_notes: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def status_value(cls, value: str | None):
        if value is not None and value not in STATUSES: raise ValueError("Unsupported asset status")
        return value

    @field_validator("ci_category")
    @classmethod
    def category_value(cls, value: str | None):
        if value is not None and value not in CATEGORIES: raise ValueError("Unsupported CI category")
        return value

    @field_validator("condition")
    @classmethod
    def condition_value(cls, value: str | None):
        if value is not None and value not in CONDITIONS: raise ValueError("Unsupported asset condition")
        return value


class LifecycleTransition(BaseModel):
    status: str
    reason: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def lifecycle_status(cls, value: str):
        if value not in STATUSES: raise ValueError("Unsupported lifecycle status")
        return value


class LifecycleEventResponse(BaseModel):
    id: UUID
    previous_status: str | None
    new_status: str
    reason: str | None
    notes: str | None
    changed_by_name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class AssetResponse(BaseModel):
    id: UUID
    asset_number: str
    device_id: UUID | None
    name: str
    asset_tag: str | None
    device_type: str
    status: str
    ci_category: str
    vendor: str | None
    model: str | None
    serial_number: str | None
    hostname: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    department_id: UUID | None
    department: str | None
    room_id: UUID | None
    location: str | None
    business_owner: str | None
    technical_owner: str | None
    description: str | None
    condition: str | None
    acquisition_date: date | None
    received_date: date | None
    deployment_date: date | None
    retirement_date: date | None
    retirement_reason: str | None
    warranty_start: date | None
    warranty_end: date | None
    expected_replacement_date: date | None
    lifecycle_notes: str | None
    warranty_status: str
    asset_age_months: int | None
    lifecycle_history: list[LifecycleEventResponse] = []
    acquisition: dict | None = None
    source: str
    field_sources: dict
    health: str
    last_seen: datetime | None
    relationships: dict = {}
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)
