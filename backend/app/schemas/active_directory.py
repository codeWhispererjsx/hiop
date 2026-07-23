from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.active_directory import (
    ADAuthenticationMethod,
    ADConflictPolicy,
    ADMatchCandidateType,
    ADMatchLevel,
    ADMatchStatus,
    ADObjectType,
    ADRecommendedAction,
    ADReviewStatus,
    ADSyncRunStatus,
    ADSyncStatus,
)


class ActiveDirectoryConnectionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    domain_name: str = Field(..., min_length=2, max_length=255)
    server_host: str = Field(..., min_length=2, max_length=255)
    server_port: int = Field(default=389, ge=1, le=65535)
    use_ssl: bool = False
    use_start_tls: bool = False
    base_dn: str = Field(..., min_length=3, max_length=255)
    user_search_base: str | None = Field(default=None, max_length=255)
    computer_search_base: str | None = Field(default=None, max_length=255)
    group_search_base: str | None = Field(default=None, max_length=255)
    bind_username: str | None = Field(default=None, max_length=255)
    bind_secret: str | None = Field(default=None, max_length=1024)
    authentication_method: ADAuthenticationMethod = ADAuthenticationMethod.SIMPLE
    connection_timeout_seconds: int = Field(default=10, ge=1, le=300)
    page_size: int = Field(default=500, ge=1, le=5000)
    enabled: bool = True
    verify_tls: bool = True
    ca_certificate_reference: str | None = Field(default=None, max_length=255)

    @field_validator("domain_name")
    @classmethod
    def validate_domain(cls, v: str) -> str:
        v = v.strip()
        if not v or " " in v:
            raise ValueError("Domain name must be a valid non-empty string without spaces.")
        return v

    @field_validator("base_dn")
    @classmethod
    def validate_base_dn(cls, v: str) -> str:
        v = v.strip()
        if "=" not in v:
            raise ValueError("Base DN must contain key=value pairs (e.g. DC=hotel,DC=internal).")
        return v


class ActiveDirectoryConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=100)
    domain_name: str | None = Field(default=None, min_length=2, max_length=255)
    server_host: str | None = Field(default=None, min_length=2, max_length=255)
    server_port: int | None = Field(default=None, ge=1, le=65535)
    use_ssl: bool | None = None
    use_start_tls: bool | None = None
    base_dn: str | None = Field(default=None, min_length=3, max_length=255)
    user_search_base: str | None = Field(default=None, max_length=255)
    computer_search_base: str | None = Field(default=None, max_length=255)
    group_search_base: str | None = Field(default=None, max_length=255)
    bind_username: str | None = Field(default=None, max_length=255)
    authentication_method: ADAuthenticationMethod | None = None
    connection_timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    page_size: int | None = Field(default=None, ge=1, le=5000)
    enabled: bool | None = None
    verify_tls: bool | None = None
    ca_certificate_reference: str | None = Field(default=None, max_length=255)


class ActiveDirectorySecretUpdate(BaseModel):
    bind_secret: str = Field(..., min_length=1, max_length=1024)


class ActiveDirectoryConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    domain_name: str
    server_host: str
    server_port: int
    use_ssl: bool
    use_start_tls: bool
    base_dn: str
    user_search_base: str | None = None
    computer_search_base: str | None = None
    group_search_base: str | None = None
    bind_username: str | None = None
    has_bind_secret: bool = False
    authentication_method: str
    connection_timeout_seconds: int
    page_size: int
    enabled: bool
    verify_tls: bool
    ca_certificate_reference: str | None = None
    last_tested_at: datetime | None = None
    last_test_status: str | None = None
    last_test_message: str | None = None
    created_by: str | None = None
    updated_by: str | None = None
    created_at: datetime
    updated_at: datetime


class ActiveDirectorySyncConfigurationUpdate(BaseModel):
    sync_users_enabled: bool | None = None
    sync_computers_enabled: bool | None = None
    sync_groups_enabled: bool | None = None
    sync_interval_minutes: int | None = Field(default=None, ge=1, le=14400)
    auto_create_users: bool | None = None
    auto_disable_missing_users: bool | None = None
    auto_create_devices: bool | None = None
    auto_update_devices: bool | None = None
    sync_group_memberships: bool | None = None
    department_mapping_enabled: bool | None = None
    organizational_unit_mapping_enabled: bool | None = None
    dry_run_default: bool | None = None
    conflict_policy: ADConflictPolicy | None = None
    enabled: bool | None = None


class ActiveDirectorySyncConfigurationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    sync_users_enabled: bool
    sync_computers_enabled: bool
    sync_groups_enabled: bool
    sync_interval_minutes: int
    auto_create_users: bool
    auto_disable_missing_users: bool
    auto_create_devices: bool
    auto_update_devices: bool
    sync_group_memberships: bool
    department_mapping_enabled: bool
    organizational_unit_mapping_enabled: bool
    dry_run_default: bool
    conflict_policy: str
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ActiveDirectoryObjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    object_guid: str
    object_sid: str | None = None
    object_type: str
    distinguished_name: str
    sam_account_name: str | None = None
    user_principal_name: str | None = None
    common_name: str | None = None
    display_name: str | None = None
    dns_hostname: str | None = None
    email: str | None = None
    department: str | None = None
    job_title: str | None = None
    operating_system: str | None = None
    operating_system_version: str | None = None
    organizational_unit: str | None = None
    description: str | None = None
    enabled: bool
    last_logon_at: datetime | None = None
    when_created: datetime | None = None
    when_changed: datetime | None = None
    raw_attributes: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    sync_status: str
    review_status: str
    matched_user_id: str | None = None
    matched_device_id: str | None = None
    created_at: datetime
    updated_at: datetime


class ActiveDirectorySyncRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    trigger_type: str
    triggered_by: str | None = None
    dry_run: bool
    users_seen: int
    computers_seen: int
    groups_seen: int
    created_objects: int
    updated_objects: int
    unchanged_objects: int
    missing_objects: int
    conflicts: int
    errors_count: int
    duration_ms: int | None = None
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class ActiveDirectoryMatchCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    directory_object_id: str
    candidate_type: str
    candidate_user_id: str | None = None
    candidate_device_id: str | None = None
    match_score: float
    match_level: str
    match_status: str
    matching_fields: list[Any]
    conflicting_fields: list[Any]
    evidence: dict[str, Any]
    recommended_action: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PaginatedADConnections(BaseModel):
    items: list[ActiveDirectoryConnectionRead]
    total: int
    offset: int
    limit: int


class PaginatedADObjects(BaseModel):
    items: list[ActiveDirectoryObjectRead]
    total: int
    offset: int
    limit: int


class PaginatedADSyncRuns(BaseModel):
    items: list[ActiveDirectorySyncRunRead]
    total: int
    offset: int
    limit: int


class PaginatedADMatchCandidates(BaseModel):
    items: list[ActiveDirectoryMatchCandidateRead]
    total: int
    offset: int
    limit: int
