from uuid import UUID

from pydantic import BaseModel
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
    network: str
