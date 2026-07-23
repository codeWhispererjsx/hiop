from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


DOMAIN_PATTERN = re.compile(r"^(?=.{1,255}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
HOST_PATTERN = re.compile(r"^(?=.{1,255}$)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
DN_COMPONENT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9-]*=.+$")


def _domain(value: str) -> str:
    value = value.strip().lower()
    if not DOMAIN_PATTERN.fullmatch(value):
        raise ValueError("Domain name must be a valid DNS domain.")
    return value


def _host(value: str) -> str:
    value = value.strip().lower()
    if not HOST_PATTERN.fullmatch(value):
        raise ValueError("Server host must be a valid hostname or IP address.")
    return value


def _dn(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    parts = [part.strip() for part in value.split(",")]
    if not parts or any(not DN_COMPONENT_PATTERN.fullmatch(part) for part in parts):
        raise ValueError("Distinguished name must contain comma-separated key=value components.")
    return value


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
        return _domain(v)

    @field_validator("server_host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        return _host(v)

    @field_validator("base_dn", "user_search_base", "computer_search_base", "group_search_base")
    @classmethod
    def validate_base_dn(cls, v: str | None) -> str | None:
        return _dn(v)

    @model_validator(mode="after")
    def validate_transport(self):
        if self.use_ssl and self.use_start_tls:
            raise ValueError("LDAPS and StartTLS cannot both be enabled.")
        if self.authentication_method == ADAuthenticationMethod.ANONYMOUS and (
            self.bind_username or self.bind_secret
        ):
            raise ValueError("Anonymous authentication cannot include bind credentials.")
        return self


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

    @field_validator("domain_name")
    @classmethod
    def validate_domain(cls, v: str | None) -> str | None:
        return _domain(v) if v is not None else None

    @field_validator("server_host")
    @classmethod
    def validate_host(cls, v: str | None) -> str | None:
        return _host(v) if v is not None else None

    @field_validator("base_dn", "user_search_base", "computer_search_base", "group_search_base")
    @classmethod
    def validate_dn(cls, v: str | None) -> str | None:
        return _dn(v)

    @model_validator(mode="after")
    def validate_transport(self):
        if self.use_ssl is True and self.use_start_tls is True:
            raise ValueError("LDAPS and StartTLS cannot both be enabled.")
        return self


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
    last_successful_bind_at: datetime | None = None
    last_failure_at: datetime | None = None
    failure_count: int = 0
    certificate_expiry: datetime | None = None
    server_reported_domain: str | None = None
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
    checkpoints: dict[str, str] = Field(default_factory=dict)
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
    missing_since: datetime | None = None
    last_sync_run_id: str | None = None
    sync_status: str
    review_status: str
    matched_user_id: str | None = None
    matched_device_id: UUID | None = None
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
    sync_mode: str = "full"
    object_types: list[str] = Field(default_factory=list)
    checkpoint_before: dict[str, Any] = Field(default_factory=dict)
    checkpoint_after: dict[str, Any] = Field(default_factory=dict)
    per_type_status: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    dry_run_results: dict[str, Any] = Field(default_factory=dict)
    cancel_requested_at: datetime | None = None
    users_seen: int
    computers_seen: int
    groups_seen: int
    created_objects: int
    updated_objects: int
    unchanged_objects: int
    missing_objects: int
    restored_objects: int = 0
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
    candidate_device_id: UUID | None = None
    candidate_discovery_id: UUID | None = None
    candidate_department_id: UUID | None = None
    candidate_role_id: str | None = None
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


class ActiveDirectoryMatchRequest(BaseModel):
    object_types: list[Literal["user", "computer", "group"]] | None = None
    recompute: bool = False
    dry_run: bool = False
    limit: int = Field(default=1000, ge=1, le=100000)


class ActiveDirectoryCandidateReview(BaseModel):
    candidate_id: str


class ActiveDirectoryResolveRequest(BaseModel):
    action: Literal[
        "link_existing_user", "create_new_user", "enrich_existing_user",
        "review_disable", "link_existing_device", "create_new_device",
        "enrich_existing_device", "link_discovery", "review_retire",
        "suggest_role_mapping", "ignore", "conflict",
    ]
    candidate_id: str | None = None
    approved_fields: list[str] = Field(default_factory=list, max_length=20)
    device: dict[str, Any] | None = None
    role: Literal["admin", "technician", "staff"] | None = None
    active: bool | None = None
    confirm: bool = False
    confirm_privileged_role: bool = False


class ActiveDirectoryBulkReviewRequest(BaseModel):
    object_ids: list[str] = Field(min_length=1, max_length=100)
    action: Literal["link_existing_user", "link_existing_device", "ignore"]
    confirm: bool = False


class ActiveDirectoryDepartmentMappingWrite(BaseModel):
    source_value: str = Field(min_length=1, max_length=255)
    department_id: UUID
    priority: int = Field(default=100, ge=0, le=10000)
    enabled: bool = True


class ActiveDirectoryOUMappingWrite(BaseModel):
    pattern: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9 _.,=*\-]+$")
    department_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None
    device_category: str | None = Field(default=None, max_length=80)
    user_category: str | None = Field(default=None, max_length=80)
    priority: int = Field(default=100, ge=0, le=10000)
    enabled: bool = True


class ActiveDirectoryGroupRoleMappingWrite(BaseModel):
    source_group: str = Field(min_length=1, max_length=255)
    target_role: Literal["admin", "technician", "staff"]
    priority: int = Field(default=100, ge=0, le=10000)
    enabled: bool = True
    requires_confirmation: bool = True


class ActiveDirectoryMappingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    connection_id: str
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime
    source_value: str | None = None
    source_group: str | None = None
    pattern: str | None = None
    department_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    room_id: UUID | None = None
    network_zone_id: UUID | None = None
    device_category: str | None = None
    user_category: str | None = None
    target_role: str | None = None
    requires_confirmation: bool | None = None


class ActiveDirectoryReconciliationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    directory_object_id: str
    action: str
    status: str
    target_user_id: str | None = None
    target_device_id: UUID | None = None
    before_values: dict[str, Any]
    after_values: dict[str, Any]
    safe_error: str | None = None
    retryable: bool
    reviewed_by: str | None = None
    reviewed_at: datetime


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


class SafeLdapError(BaseModel):
    category: str
    message: str
    retryable: bool = False


class ConnectionTestStage(BaseModel):
    name: str
    status: str
    message: str
    duration_ms: int = 0


class ActiveDirectoryConnectionTestResponse(BaseModel):
    overall_status: str
    connection_id: str
    stages: list[ConnectionTestStage]
    warnings: list[str] = []
    error: SafeLdapError | None = None
    tested_at: datetime
    duration_ms: int


class ActiveDirectoryRootDseResponse(BaseModel):
    default_naming_context: str | None = None
    root_domain_naming_context: str | None = None
    configuration_naming_context: str | None = None
    schema_naming_context: str | None = None
    supported_ldap_versions: list[str] = []
    supported_sasl_mechanisms: list[str] = []
    dns_host_name: str | None = None
    server_name: str | None = None
    appears_active_directory: bool
    ldap_v3_supported: bool
    warnings: list[str] = []


class DirectoryUserPreview(BaseModel):
    object_guid: str | None = None
    object_sid: str | None = None
    sam_account_name: str | None = None
    user_principal_name: str | None = None
    display_name: str | None = None
    email: str | None = None
    department: str | None = None
    job_title: str | None = None
    distinguished_name: str | None = None
    organizational_unit: str | None = None
    group_memberships: list[str] = []
    enabled: bool
    last_logon_at: datetime | None = None
    when_created: datetime | None = None
    when_changed: datetime | None = None
    description: str | None = None
    parse_warnings: list[str] = []


class DirectoryComputerPreview(BaseModel):
    object_guid: str | None = None
    object_sid: str | None = None
    sam_account_name: str | None = None
    dns_hostname: str | None = None
    operating_system: str | None = None
    operating_system_version: str | None = None
    distinguished_name: str | None = None
    organizational_unit: str | None = None
    description: str | None = None
    managed_by: str | None = None
    enabled: bool
    last_logon_at: datetime | None = None
    when_created: datetime | None = None
    when_changed: datetime | None = None
    parse_warnings: list[str] = []


class DirectoryGroupPreview(BaseModel):
    object_guid: str | None = None
    object_sid: str | None = None
    sam_account_name: str | None = None
    common_name: str | None = None
    distinguished_name: str | None = None
    organizational_unit: str | None = None
    description: str | None = None
    group_type: dict[str, Any]
    members: list[str] = []
    members_truncated: bool = False
    member_count_returned: int = 0
    when_created: datetime | None = None
    when_changed: datetime | None = None
    parse_warnings: list[str] = []


class DirectoryPreviewResponse(BaseModel):
    object_type: str
    items: list[DirectoryUserPreview | DirectoryComputerPreview | DirectoryGroupPreview]
    returned: int
    truncated: bool
    page_count: int
    warnings: list[str] = []


class ActiveDirectorySyncRequest(BaseModel):
    sync_mode: Literal["full", "incremental"] = "incremental"
    dry_run: bool | None = None
    object_types: list[Literal["user", "computer", "group"]] | None = None
    limit: int | None = Field(default=None, ge=1, le=1_000_000)

    @field_validator("object_types")
    @classmethod
    def unique_types(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Object types must not contain duplicates.")
        return value


class ActiveDirectorySyncAccepted(BaseModel):
    sync_run_id: str
    status: str
    accepted_configuration: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class ActiveDirectorySyncErrorRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sync_run_id: str
    object_type: str | None = None
    safe_object_reference: str | None = None
    stage: str
    error_code: str
    safe_message: str
    retryable: bool
    created_at: datetime


class ActiveDirectoryObjectChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    directory_object_id: str
    sync_run_id: str
    change_type: str
    changed_fields: list[str]
    before_values: dict[str, Any]
    after_values: dict[str, Any]
    detected_at: datetime


class PaginatedADSyncErrors(BaseModel):
    items: list[ActiveDirectorySyncErrorRead]
    total: int
    offset: int
    limit: int


class PaginatedADObjectChanges(BaseModel):
    items: list[ActiveDirectoryObjectChangeRead]
    total: int
    offset: int
    limit: int


class ActiveDirectorySyncSummary(BaseModel):
    sync_run_id: str
    status: str
    sync_mode: str
    dry_run: bool
    counts: dict[str, int]
    per_object_type: dict[str, Any]
    duration_ms: int | None = None
    checkpoint_before: dict[str, Any]
    checkpoint_after: dict[str, Any]
