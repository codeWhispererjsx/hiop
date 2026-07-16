from pydantic import BaseModel, Field, field_validator
from typing import Optional
from uuid import UUID
from datetime import datetime

class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=5000)
    priority: str = Field(default="Medium", pattern="^(Low|Medium|High)$")
    device_id: UUID | None = None

    @field_validator("title", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Value must contain at least 3 non-whitespace characters")
        return value


class TicketUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=200)
    description: Optional[str] = Field(default=None, min_length=3, max_length=5000)
    priority: Optional[str] = Field(default=None, pattern="^(Low|Medium|High)$")
    status: Optional[str] = Field(default=None, pattern="^(Open|In Progress|Closed)$")
    assigned_to: Optional[str] = Field(default=None, max_length=36)
    device_id: UUID | None = None

    @field_validator("title", "description")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None


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
