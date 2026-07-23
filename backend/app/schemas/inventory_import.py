from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.imports.columns import CANONICAL_FIELDS
from app.models.inventory_import import ImportExecutionStatus, ImportSessionStatus, ImportValidationStatus


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
    matching_state: str
    match_summary: dict[str, Any]
    execution_summary: dict[str, Any]
    plan_version: int
    plan_locked_at: datetime | None
    finalized_by: str | None
    finalization_started_at: datetime | None
    finalization_completed_at: datetime | None
    rollback_by: str | None
    rollback_at: datetime | None
    retry_count: int
    validation_summary: dict[str, int] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ImportUploadResponse(BaseModel):
    session: ImportSessionResponse
    preview: dict[str, Any]


class ImportSessionPage(BaseModel):
    items: list[ImportSessionResponse]
    total: int
    page: int
    page_size: int
    pages: int


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
    device_type: str | None
    raw_data: dict[str, Any]
    normalized_data: dict[str, Any]
    errors: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    validation_status: ImportValidationStatus
    imported_at: datetime
    resolution_action: str | None
    linked_device_id: UUID | None
    linked_discovery_id: UUID | None
    resolved_by: str | None
    resolved_at: datetime | None
    final_disposition: str | None
    approved_changes: dict[str, Any]


class ImportedDevicePage(BaseModel):
    items: list[ImportedDeviceResponse]
    total: int
    page: int
    page_size: int
    pages: int


class MatchCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    import_session_id: UUID
    imported_device_id: UUID
    candidate_type: str
    candidate_device_id: UUID | None
    candidate_discovery_id: UUID | None
    candidate_imported_device_id: UUID | None
    match_score: int
    match_level: str
    match_status: str
    evidence: list[dict[str, Any]]
    conflicting_fields: list[dict[str, Any]]
    matching_fields: list[str]
    recommended_action: str
    reviewed_by: str | None
    reviewed_at: datetime | None


class MatchCandidatePage(BaseModel):
    items: list[MatchCandidateResponse]
    total: int
    page: int
    page_size: int


class CandidateResolutionRequest(BaseModel):
    candidate_id: UUID


class LocationReviewRequest(BaseModel):
    action: str = Field(pattern="^(accept|reject|override)$")
    department_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None


class LocationSuggestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    imported_device_id: UUID
    department_id: UUID | None
    building_id: UUID | None
    floor_id: UUID | None
    room_id: UUID | None
    network_zone_id: UUID | None
    confidence_score: int
    evidence: list[dict[str, Any]]
    conflicts: list[dict[str, Any]]
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None


class FinalDispositionRequest(BaseModel):
    disposition: str = Field(pattern="^(create_new|link_existing|enrich_existing|merge_reviewed|link_discovery|skip)$")
    approved_fields: list[str] = Field(default_factory=list, max_length=25)
    approved_overwrites: list[str] = Field(default_factory=list, max_length=10)


class FinalizeRequest(BaseModel):
    plan_version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=12, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    confirm_inventory_mutation: bool
    confirm_rollback_limits: bool


class RollbackRequest(BaseModel):
    confirmation: str = Field(pattern="^ROLLBACK$")


class ImportExecutionResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    import_session_id: UUID
    imported_device_id: UUID
    action: str
    status: ImportExecutionStatus
    target_device_id: UUID | None
    target_discovery_id: UUID | None
    plan: dict[str, Any]
    before_snapshot: dict[str, Any]
    after_snapshot: dict[str, Any]
    error_code: str | None
    safe_error_message: str | None
    retry_count: int
    started_at: datetime | None
    completed_at: datetime | None
    rolled_back_at: datetime | None


class ImportExecutionResultPage(BaseModel):
    items: list[ImportExecutionResultResponse]
    total: int
    page: int
    page_size: int
    pages: int
