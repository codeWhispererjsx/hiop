from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime

class TicketCreate(BaseModel):
    title: str
    description: str
    priority: str = "Medium"
    device_id: UUID | None = None


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None
    device_id: UUID | None = None


class TicketResponse(BaseModel):
    id: UUID
    title: str
    description: str
    priority: str
    status: str
    reported_by: str
    assigned_to: Optional[str] = None
    device_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True
    }
