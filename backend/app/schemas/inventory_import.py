from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.imports.columns import CANONICAL_FIELDS
from app.models.inventory_import import ImportSessionStatus, ImportValidationStatus


class ImportSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    original_filename: str
    import_type: str
    file_format: str
    uploaded_by: str | None
    uploaded_at: datetime
    processing_started_at: datetime | None
    processing_completed_at: datetime | None
    status: ImportSessionStatus
    total_rows: int
    processed_rows: int
    successful_rows: int
    failed_rows: int
    duplicate_rows: int
    matched_rows: int
    skipped_rows: int
    error_summary: str | None
    selected_worksheet: str | None
    created_at: datetime
    updated_at: datetime


class ImportUploadResponse(BaseModel):
    session: ImportSessionResponse
    preview: dict[str, Any]


class ImportMappingRequest(BaseModel):
    mapping: dict[str, str | None]
    worksheet: str | None = Field(default=None, max_length=255)

    @field_validator("mapping")
    @classmethod
    def bounded_mapping(cls, value):
        if not value or len(value) > 100:
            raise ValueError("Mapping must contain between 1 and 100 columns")
        if any(target is not None and target not in CANONICAL_FIELDS for target in value.values()):
            raise ValueError("Mapping contains an unsupported canonical field")
        return value


class ImportedDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    import_session_id: UUID
    source_row_number: int
    asset_tag: str | None
    hostname: str | None
    ip_address: str | None
    mac_address: str | None
    department_name: str | None
    building_name: str | None
    floor_name: str | None
    room_name: str | None
    network_zone: str | None
    vendor: str | None
    brand: str | None
    model: str | None
    serial_number: str | None
    inventory_status: str | None
    notes: str | None
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    validation_status: ImportValidationStatus
    imported_at: datetime


class ImportedDevicePage(BaseModel):
    items: list[ImportedDeviceResponse]
    total: int
    page: int
    page_size: int
    pages: int
