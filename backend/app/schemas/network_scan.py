from uuid import UUID

from pydantic import BaseModel


class NetworkScanCreate(BaseModel):
    device_id: UUID


class NetworkScanResponse(BaseModel):
    id: UUID
    device_id: UUID
    ip_address: str
    status: str
    response_time: int | None

    model_config = {
        "from_attributes": True
    }