from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

BuildingStatus = Literal["active", "maintenance", "inactive"]
ZoneStatus = Literal["active", "maintenance", "inactive"]
ZoneType = Literal["guest_rooms", "lobby", "ballroom", "kitchen", "restaurant", "office", "reception", "conference", "spa", "gym", "pool", "outdoor", "parking", "back_office", "it", "security", "laundry", "engineering", "storage", "unknown"]

class BuildingWrite(BaseModel):
    property_id: UUID
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    description: str | None = Field(default=None, max_length=255)
    number_of_floors: int | None = Field(default=None, ge=0, le=1000)
    status: BuildingStatus = "active"

class BuildingRead(BuildingWrite):
    id: UUID
    is_active: bool
    class Config: from_attributes = True

class FloorWrite(BaseModel):
    building_id: UUID
    name: str = Field(min_length=1, max_length=120)
    floor_number: int | None = Field(default=None, ge=-100, le=1000)
    display_name: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=255)
    zone_count: int = Field(default=0, ge=0)
    status: BuildingStatus = "active"

class FloorRead(FloorWrite):
    id: UUID
    is_active: bool
    class Config: from_attributes = True

class ZoneWrite(BaseModel):
    floor_id: UUID
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, max_length=40)
    type: ZoneType = "unknown"
    description: str | None = Field(default=None, max_length=255)
    status: ZoneStatus = "active"

class ZoneRead(ZoneWrite):
    id: UUID
    is_active: bool
    class Config: from_attributes = True
