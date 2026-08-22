from uuid import UUID
from pydantic import BaseModel, Field, field_validator


SERVICE_STATUSES = {"operational", "degraded", "outage", "unknown"}
INCIDENT_STATUSES = {"new", "acknowledged", "in_progress", "on_hold", "resolved", "closed"}
PRIORITIES = {"low", "medium", "high", "critical"}
CATEGORIES = {"network", "hardware", "software", "pos", "pms", "wifi", "printer", "security_system", "telephony", "other"}


class ServiceWrite(BaseModel):
    property_id: UUID
    name: str = Field(min_length=2, max_length=160)
    code: str = Field(pattern=r"^[A-Za-z0-9_-]{2,50}$")
    description: str | None = Field(None, max_length=255)
    status: str = "unknown"
    criticality: str = "medium"
    owner_team: str | None = Field(None, max_length=160)
    owner_user_id: str | None = None
    notes: str | None = Field(None, max_length=4000)
    department_id: UUID | None = None
    location_type: str | None = None
    location_id: UUID | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value not in SERVICE_STATUSES: raise ValueError("Unsupported service status")
        return value


class ServicePatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=160)
    description: str | None = Field(None, max_length=255)
    status: str | None = None
    criticality: str | None = None
    owner_team: str | None = Field(None, max_length=160)
    owner_user_id: str | None = None
    notes: str | None = Field(None, max_length=4000)
    department_id: UUID | None = None
    location_type: str | None = None
    location_id: UUID | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, value):
        if value is not None and value not in SERVICE_STATUSES: raise ValueError("Unsupported service status")
        return value


class OperationalIncidentWrite(BaseModel):
    property_id: UUID
    title: str = Field(min_length=3, max_length=180)
    description: str | None = Field(None, max_length=10000)
    priority: str = "medium"
    severity: str = "medium"
    category: str = "other"
    assigned_team: str | None = Field(None, max_length=160)
    assigned_technician_id: str | None = None
    requester_id: str | None = None
    asset_id: UUID | None = None
    device_id: UUID | None = None
    service_id: UUID | None = None
    department_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    room_id: UUID | None = None
    alert_id: UUID | None = None

    @field_validator("priority", "severity")
    @classmethod
    def valid_urgency(cls, value):
        if value not in PRIORITIES: raise ValueError("Unsupported priority or severity")
        return value

    @field_validator("category")
    @classmethod
    def valid_category(cls, value):
        if value not in CATEGORIES: raise ValueError("Unsupported incident category")
        return value


class IncidentPatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=180)
    description: str | None = Field(None, max_length=10000)
    priority: str | None = None
    severity: str | None = None
    category: str | None = None
    assigned_team: str | None = Field(None, max_length=160)
    assigned_technician_id: str | None = None
    service_id: UUID | None = None
    asset_id: UUID | None = None


class IncidentAssignmentWrite(BaseModel):
    assigned_technician_id: str
    assigned_team: str | None = Field(None, max_length=160)


class TransitionWrite(BaseModel):
    reason: str | None = Field(None, max_length=5000)
    resolution_summary: str | None = Field(None, max_length=10000)
    root_cause_notes: str | None = Field(None, max_length=10000)
    follow_up_notes: str | None = Field(None, max_length=10000)
    closure_notes: str | None = Field(None, max_length=10000)


class NoteWrite(BaseModel):
    note: str = Field(min_length=2, max_length=10000)


class RelationshipWrite(BaseModel):
    asset_id: UUID
    relationship_type: str = Field("supports", max_length=30)
