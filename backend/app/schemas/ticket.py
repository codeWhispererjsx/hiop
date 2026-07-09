from pydantic import BaseModel
from typing import Optional


class TicketCreate(BaseModel):
    title: str
    description: str
    priority: str = "Medium"


class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to: Optional[str] = None


class TicketResponse(BaseModel):
    id: str
    title: str
    description: str
    priority: str
    status: str
    reported_by: str
    assigned_to: Optional[str] = None

    model_config = {
        "from_attributes": True
    }