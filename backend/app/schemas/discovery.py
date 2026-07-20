from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.discovered_device import DiscoveryStatus, ReviewStatus, RunStatus
from app.schemas.device import DeviceResponse


class DiscoveredDeviceResponse(BaseModel):
    id: UUID
    ip_address: str
    mac_address: str | None
    hostname: str | None
    vendor: str | None
    operating_system_guess: str | None
    device_type_guess: str | None
    network_zone_id: UUID | None
    subnet: str | None
    discovery_method: str
    first_seen_at: datetime
    last_seen_at: datetime
    times_seen: int
    response_time: float | None
    status: DiscoveryStatus
    review_status: ReviewStatus
    confidence_score: float | None
    approved_device_id: UUID | None
    reviewed_by: str | None
    reviewed_at: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DiscoveryPage(BaseModel):
    items: list[DiscoveredDeviceResponse]
    total: int
    page: int
    page_size: int
    pages: int


class DiscoveryRunResponse(BaseModel):
    id: UUID
    started_at: datetime
    completed_at: datetime | None
    status: RunStatus
    range_scanned: str | None
    hosts_attempted: int
    hosts_responded: int
    new_devices: int
    matched_devices: int
    updated_devices: int
    error_count: int
    duration: float | None
    trigger_type: str
    triggered_by: str | None
    error_summary: str | None

    model_config = ConfigDict(from_attributes=True)


class DiscoveryStatsResponse(BaseModel):
    total_devices: int
    online: int
    offline: int
    unknown: int
    pending_review: int
    matched_inventory: int
    total_runs: int
    last_run: DiscoveryRunResponse | None


class RunDiscoveryRequest(BaseModel):
    range_scanned: str = Field(min_length=9, max_length=64)

    @field_validator("range_scanned")
    @classmethod
    def strip_range(cls, value: str) -> str:
        return value.strip()


class InventoryApproval(BaseModel):
    asset_tag: str = Field(min_length=1, max_length=80)
    hostname: str | None = Field(default=None, min_length=1, max_length=253)
    device_type: str | None = Field(default=None, min_length=1, max_length=80)
    ip_address: str | None = Field(default=None, min_length=3, max_length=45)
    mac_address: str | None = Field(default=None, min_length=17, max_length=17)
    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    serial_number: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=160)
    inventory_status: str = Field(default="Active", pattern="^(Active|Inactive)$")
    department_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None

    @field_validator(
        "asset_tag", "hostname", "device_type", "brand", "model",
        "serial_number", "department", "location",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value


class ApprovalResponse(BaseModel):
    discovery: DiscoveredDeviceResponse
    device: DeviceResponse


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class BulkApprovalItem(BaseModel):
    discovery_id: UUID
    inventory: InventoryApproval


class BulkApproveRequest(BaseModel):
    items: list[BulkApprovalItem] = Field(min_length=1, max_length=100)

    @field_validator("items")
    @classmethod
    def unique_items(cls, value: list[BulkApprovalItem]) -> list[BulkApprovalItem]:
        ids = [item.discovery_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Discovery IDs must be unique")
        return value


class BulkReviewRequest(BaseModel):
    discovery_ids: list[UUID] = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("discovery_ids")
    @classmethod
    def unique_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("Discovery IDs must be unique")
        return value

    @field_validator("reason")
    @classmethod
    def clean_reason(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class BulkActionResponse(BaseModel):
    processed: int
    discovery_ids: list[UUID]
