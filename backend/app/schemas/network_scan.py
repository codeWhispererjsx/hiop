from uuid import UUID

from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class NetworkScanCreate(BaseModel):
    device_id: UUID


class NetworkScanResponse(BaseModel):
    id: UUID
    device_id: UUID
    ip_address: str
    status: str
    response_time: float | None
    scanned_at: datetime

    model_config = {
        "from_attributes": True
    }

class NetworkRangeScan(BaseModel):
    network: str = Field(min_length=3, max_length=64)

    @field_validator("network")
    @classmethod
    def valid_network(cls, value: str) -> str:
        from ipaddress import ip_network
        return str(ip_network(value.strip(), strict=False))
