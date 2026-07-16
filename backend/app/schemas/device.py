from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DeviceCreate(BaseModel):
    asset_tag: str
    hostname: str
    device_type: str
    brand: str
    model: str
    serial_number: str
    department: str
    location: str
    ip_address: str
    mac_address: str
    inventory_status: str = Field(default="Active", pattern="^(Active|Inactive)$")
    status: str | None = None
    department_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None


class DeviceUpdate(BaseModel):
    asset_tag: str | None = None
    hostname: str | None = None
    device_type: str | None = None
    brand: str | None = None
    model: str | None = None
    serial_number: str | None = None
    department: str | None = None
    location: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    inventory_status: str | None = Field(default=None, pattern="^(Active|Inactive)$")
    status: str | None = None
    department_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None


class DeviceResponse(BaseModel):
    id: UUID
    asset_tag: str
    hostname: str
    device_type: str
    brand: str
    model: str
    serial_number: str
    department: str
    location: str
    ip_address: str
    mac_address: str
    inventory_status: str
    network_status: str
    status: str
    department_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None

    model_config = ConfigDict(from_attributes=True)
