from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AuditLogResponse(BaseModel):
    id: UUID
    actor: str
    action: str
    entity_type: str
    entity_id: str
    description: str
    created_at: datetime

    class Config:
        from_attributes = True


class AuditSummary(BaseModel):
    total: int = 0
    today: int = 0
    user_actions: int = 0
    device_actions: int = 0
    ticket_actions: int = 0
    security_events: int = 0


class AuditFilterOptions(BaseModel):
    actors: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int
    summary: AuditSummary
    options: AuditFilterOptions
