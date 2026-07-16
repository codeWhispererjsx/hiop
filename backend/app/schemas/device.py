from uuid import UUID

from ipaddress import ip_address
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAC_PATTERN = re.compile(r"^(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


class DeviceCreate(BaseModel):
    asset_tag: str = Field(min_length=1, max_length=80)
    hostname: str = Field(min_length=1, max_length=253)
    device_type: str = Field(min_length=1, max_length=80)
    brand: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    serial_number: str = Field(min_length=1, max_length=120)
    department: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=160)
    ip_address: str = Field(min_length=3, max_length=45)
    mac_address: str = Field(min_length=17, max_length=17)
    inventory_status: str = Field(default="Active", pattern="^(Active|Inactive)$")
    status: str | None = Field(default=None, pattern="^(Active|Inactive)$")
    department_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None

    @field_validator("asset_tag", "hostname", "device_type", "brand", "model", "serial_number", "department", "location")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("ip_address")
    @classmethod
    def valid_ip(cls, value: str) -> str:
        return str(ip_address(value.strip()))

    @field_validator("mac_address")
    @classmethod
    def valid_mac(cls, value: str) -> str:
        value = value.strip().upper().replace("-", ":")
        if not MAC_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid MAC address")
        return value


class DeviceUpdate(BaseModel):
    asset_tag: str | None = Field(default=None, min_length=1, max_length=80)
    hostname: str | None = Field(default=None, min_length=1, max_length=253)
    device_type: str | None = Field(default=None, min_length=1, max_length=80)
    brand: str | None = Field(default=None, min_length=1, max_length=80)
    model: str | None = Field(default=None, min_length=1, max_length=120)
    serial_number: str | None = Field(default=None, min_length=1, max_length=120)
    department: str | None = Field(default=None, min_length=1, max_length=120)
    location: str | None = Field(default=None, min_length=1, max_length=160)
    ip_address: str | None = Field(default=None, min_length=3, max_length=45)
    mac_address: str | None = Field(default=None, min_length=17, max_length=17)
    inventory_status: str | None = Field(default=None, pattern="^(Active|Inactive)$")
    status: str | None = Field(default=None, pattern="^(Active|Inactive)$")
    department_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None

    @field_validator("asset_tag", "hostname", "device_type", "brand", "model", "serial_number", "department", "location")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be blank")
        return value

    @field_validator("ip_address")
    @classmethod
    def valid_optional_ip(cls, value: str | None) -> str | None:
        return None if value is None else str(ip_address(value.strip()))

    @field_validator("mac_address")
    @classmethod
    def valid_optional_mac(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper().replace("-", ":")
        if not MAC_PATTERN.fullmatch(value):
            raise ValueError("Enter a valid MAC address")
        return value


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
