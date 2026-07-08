from uuid import UUID
from pydantic import BaseModel

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
    status: str = "Active"


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
    status: str | None = None


class DeviceResponse(DeviceCreate):
    id: UUID

    class Config:
        from_attributes = True