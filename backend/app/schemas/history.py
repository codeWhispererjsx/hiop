from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    id: UUID
    device_id: UUID
    previous_status: str
    current_status: str
    message: str
    created_at: datetime
    acknowledged: bool

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    id: UUID
    actor: str
    action: str
    entity_type: str
    entity_id: str
    description: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
