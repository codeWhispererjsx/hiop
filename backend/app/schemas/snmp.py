"""Validated, secret-safe transport schemas for the SNMP foundation."""
import ipaddress
import re
from datetime import datetime
from typing import Any
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.snmp import (
    SNMPAuthProtocol, SNMPCollectionType, SNMPDataType, SNMPDeviceType,
    SNMPPrivacyProtocol, SNMPSecurityLevel, SNMPTransport, SNMPVersion,
)

OID_PATTERN = re.compile(r"^(?:0|1|2)(?:\.(?:0|[1-9][0-9]{0,9}))+$")
HOST_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)
METRIC_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,119}$")
APPROVED_TRANSFORMS = {"identity", "scale", "timeticks_to_seconds", "enum_map", "bytes_to_bits"}


def validate_oid(value: str) -> str:
    value = value.strip().lstrip(".")
    if not OID_PATTERN.fullmatch(value):
        raise ValueError("OID must be a dotted numeric object identifier.")
    return value


def validate_endpoint(value: str) -> str:
    value = value.strip().lower()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        if not HOST_PATTERN.fullmatch(value):
            raise ValueError("Endpoint must be a valid IP address or hostname.")
        return value


class SNMPCredentialWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    version: SNMPVersion
    community: str | None = Field(default=None, min_length=1, max_length=512)
    username: str | None = Field(default=None, min_length=1, max_length=128)
    authentication_protocol: SNMPAuthProtocol = SNMPAuthProtocol.NONE
    authentication_secret: str | None = Field(default=None, min_length=8, max_length=512)
    privacy_protocol: SNMPPrivacyProtocol = SNMPPrivacyProtocol.NONE
    privacy_secret: str | None = Field(default=None, min_length=8, max_length=512)
    security_level: SNMPSecurityLevel = SNMPSecurityLevel.NO_AUTH_NO_PRIV
    context_name: str | None = Field(default=None, max_length=128)
    enabled: bool = True
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_version_security(self):
        community = bool(self.community)
        auth = bool(self.authentication_secret)
        privacy = bool(self.privacy_secret)
        if self.version in {SNMPVersion.V1, SNMPVersion.V2C}:
            if not community:
                raise ValueError("SNMPv1/v2c requires a community string.")
            if self.username or auth or privacy or self.authentication_protocol != SNMPAuthProtocol.NONE or self.privacy_protocol != SNMPPrivacyProtocol.NONE:
                raise ValueError("SNMPv1/v2c cannot include SNMPv3 security fields.")
            return self
        if community:
            raise ValueError("SNMPv3 cannot include a community string.")
        if not self.username:
            raise ValueError("SNMPv3 requires a username.")
        if self.security_level == SNMPSecurityLevel.NO_AUTH_NO_PRIV:
            if auth or privacy or self.authentication_protocol != SNMPAuthProtocol.NONE or self.privacy_protocol != SNMPPrivacyProtocol.NONE:
                raise ValueError("noAuthNoPriv cannot include authentication or privacy material.")
        elif self.security_level == SNMPSecurityLevel.AUTH_NO_PRIV:
            if self.authentication_protocol == SNMPAuthProtocol.NONE or not auth:
                raise ValueError("authNoPriv requires an authentication protocol and secret.")
            if self.privacy_protocol != SNMPPrivacyProtocol.NONE or privacy:
                raise ValueError("authNoPriv cannot include privacy material.")
        elif (
            self.authentication_protocol == SNMPAuthProtocol.NONE
            or not auth
            or self.privacy_protocol == SNMPPrivacyProtocol.NONE
            or not privacy
        ):
            raise ValueError("authPriv requires authentication and privacy protocols and secrets.")
        return self


class SNMPCredentialCreate(SNMPCredentialWrite):
    pass


class SNMPCredentialUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    enabled: bool | None = None
    description: str | None = Field(default=None, max_length=500)
    context_name: str | None = Field(default=None, max_length=128)


class SNMPCredentialSecretUpdate(BaseModel):
    community: str | None = Field(default=None, min_length=1, max_length=512)
    authentication_secret: str | None = Field(default=None, min_length=8, max_length=512)
    privacy_secret: str | None = Field(default=None, min_length=8, max_length=512)

    @model_validator(mode="after")
    def at_least_one(self):
        if not any((self.community, self.authentication_secret, self.privacy_secret)):
            raise ValueError("At least one replacement secret is required.")
        return self


class SNMPCredentialRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    version: str
    username: str | None
    authentication_protocol: str
    privacy_protocol: str
    security_level: str
    context_name: str | None
    enabled: bool
    description: str | None
    has_community: bool = False
    has_authentication_secret: bool = False
    has_privacy_secret: bool = False
    created_by: str | None
    updated_by: str | None
    created_at: datetime
    updated_at: datetime


class SNMPTargetCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    device_id: UUID | None = None
    discovered_device_id: UUID | None = None
    credential_id: UUID
    hostname: str | None = Field(default=None, max_length=255)
    ip_address: str = Field(max_length=45)
    port: int = Field(default=161, ge=1, le=65535)
    version: SNMPVersion
    enabled: bool = True
    polling_enabled: bool = False
    timeout_seconds: int = Field(default=5, ge=1, le=60)
    retries: int = Field(default=1, ge=0, le=10)
    transport: SNMPTransport = SNMPTransport.UDP
    context_name: str = Field(default="", max_length=128)
    network_zone_id: UUID | None = None
    location_id: UUID | None = None

    @field_validator("ip_address")
    @classmethod
    def ip_only(cls, value: str) -> str:
        try:
            return str(ipaddress.ip_address(value.strip()))
        except ValueError as error:
            raise ValueError("Target IP address is invalid.") from error

    @field_validator("hostname")
    @classmethod
    def hostname_valid(cls, value: str | None) -> str | None:
        return validate_endpoint(value) if value else value


class SNMPTargetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    credential_id: UUID | None = None
    hostname: str | None = Field(default=None, max_length=255)
    ip_address: str | None = Field(default=None, max_length=45)
    port: int | None = Field(default=None, ge=1, le=65535)
    enabled: bool | None = None
    polling_enabled: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)
    retries: int | None = Field(default=None, ge=0, le=10)
    context_name: str | None = Field(default=None, max_length=128)
    network_zone_id: UUID | None = None
    location_id: UUID | None = None

    _validate_ip = field_validator("ip_address")(lambda value: str(ipaddress.ip_address(value)) if value else value)


class SNMPTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    device_id: UUID | None
    discovered_device_id: UUID | None
    credential_id: UUID
    hostname: str | None
    ip_address: str
    port: int
    version: str
    enabled: bool
    polling_enabled: bool
    timeout_seconds: int
    retries: int
    transport: str
    context_name: str
    network_zone_id: UUID | None
    location_id: UUID | None
    last_tested_at: datetime | None
    last_test_status: str | None
    last_test_message: str | None
    last_successful_poll_at: datetime | None
    last_failed_poll_at: datetime | None
    consecutive_failures: int
    last_response_time_ms: float | None = None
    detected_sys_object_id: str | None = None
    detected_profile_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class SNMPProfileWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    vendor: str | None = Field(default=None, max_length=120)
    device_type: SNMPDeviceType = SNMPDeviceType.GENERIC
    sys_object_id_pattern: str | None = Field(default=None, max_length=255)
    sys_descr_pattern: str | None = Field(default=None, max_length=255)
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=10000)
    profile_data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sys_object_id_pattern")
    @classmethod
    def oid_prefix(cls, value: str | None) -> str | None:
        return validate_oid(value.rstrip(".*")) + (".*" if value.endswith(".*") else "") if value else value

    @field_validator("profile_data")
    @classmethod
    def no_executable_profile(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {"code", "script", "command", "eval", "exec"}
        if forbidden.intersection(key.lower() for key in value):
            raise ValueError("Profile data cannot contain executable definitions.")
        return value


class SNMPProfileCreate(SNMPProfileWrite):
    pass


class SNMPProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    vendor: str | None = Field(default=None, max_length=120)
    enabled: bool | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    profile_data: dict[str, Any] | None = None


class SNMPProfileRead(SNMPProfileWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class SNMPOIDWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    oid: str = Field(max_length=255)
    metric_key: str = Field(max_length=120)
    description: str | None = Field(default=None, max_length=500)
    data_type: SNMPDataType
    unit: str | None = Field(default=None, max_length=40)
    scale_factor: float = Field(default=1.0, gt=0, le=1_000_000)
    collection_type: SNMPCollectionType
    profile_id: UUID | None = None
    enabled: bool = True
    criticality: str = Field(default="normal", pattern=r"^(low|normal|high|critical)$")
    transform_type: str = Field(default="identity", max_length=30)

    _oid = field_validator("oid")(validate_oid)

    @field_validator("metric_key")
    @classmethod
    def metric_key_valid(cls, value: str) -> str:
        if not METRIC_KEY_PATTERN.fullmatch(value):
            raise ValueError("Metric key must use lowercase letters, numbers, dots, dashes, or underscores.")
        return value

    @field_validator("transform_type")
    @classmethod
    def approved_transform(cls, value: str) -> str:
        if value not in APPROVED_TRANSFORMS:
            raise ValueError("Transform type is not approved.")
        return value


class SNMPOIDCreate(SNMPOIDWrite):
    pass


class SNMPOIDUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    scale_factor: float | None = Field(default=None, gt=0, le=1_000_000)
    transform_type: str | None = None

    @field_validator("transform_type")
    @classmethod
    def approved_transform(cls, value: str | None) -> str | None:
        if value is not None and value not in APPROVED_TRANSFORMS:
            raise ValueError("Transform type is not approved.")
        return value


class SNMPOIDRead(SNMPOIDWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class SNMPPollingConfigurationWrite(BaseModel):
    polling_interval_seconds: int = Field(default=300, ge=30, le=86400)
    availability_poll_enabled: bool = True
    system_poll_enabled: bool = True
    interface_poll_enabled: bool = False
    performance_poll_enabled: bool = False
    inventory_poll_enabled: bool = False
    alerting_enabled: bool = False
    profile_id: UUID | None = None
    max_oids_per_poll: int = Field(default=50, ge=1, le=1000)
    max_interfaces: int = Field(default=256, ge=1, le=10000)
    stale_after_seconds: int = Field(default=900, ge=30, le=604800)
    enabled: bool = False
    availability_interval_seconds: int = Field(default=300, ge=30, le=604800)
    system_interval_seconds: int = Field(default=900, ge=30, le=604800)
    interface_inventory_interval_seconds: int = Field(default=3600, ge=30, le=604800)
    interface_performance_interval_seconds: int = Field(default=300, ge=30, le=604800)
    device_performance_interval_seconds: int = Field(default=600, ge=30, le=604800)
    jitter_seconds: int = Field(default=30, ge=0, le=3600)
    failure_threshold: int = Field(default=3, ge=1, le=100)
    recovery_threshold: int = Field(default=2, ge=1, le=100)
    maintenance_mode: bool = False
    maintenance_reason: str | None = Field(default=None, max_length=500)
    maintenance_ends_at: datetime | None = None


class SNMPPollingConfigurationRead(SNMPPollingConfigurationWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    target_id: UUID
    created_at: datetime
    updated_at: datetime
    maintenance_started_at: datetime | None = None
    maintenance_started_by: str | None = None
    last_scheduler_reconciliation_at: datetime | None = None


class SNMPAlertRuleWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    rule_type: str = Field(pattern=r"^(availability|authentication|poll_failures|stale_metric|metric_threshold|interface_down|interface_missing|state_change)$")
    target_id: UUID | None = None
    profile_id: UUID | None = None
    interface_id: UUID | None = None
    metric_key: str | None = Field(default=None, max_length=120)
    comparison_operator: str = Field(pattern=r"^(greater_than|greater_than_or_equal|less_than|less_than_or_equal|equal|not_equal|state_changed|missing|stale)$")
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    evaluation_window: int = Field(default=5, ge=1, le=100)
    minimum_samples: int = Field(default=1, ge=1, le=100)
    consecutive_breaches: int = Field(default=2, ge=1, le=100)
    recovery_samples: int = Field(default=2, ge=1, le=100)
    severity: str = Field(default="warning", pattern=r"^(info|warning|high|critical)$")
    enabled: bool = False
    suppress_during_maintenance: bool = True
    notification_enabled: bool = True

    @model_validator(mode="after")
    def validate_rule(self):
        threshold_ops = {"greater_than", "greater_than_or_equal", "less_than", "less_than_or_equal"}
        if self.comparison_operator in threshold_ops and self.warning_threshold is None and self.critical_threshold is None:
            raise ValueError("Threshold comparison rules require a warning or critical threshold.")
        if self.rule_type == "metric_threshold" and not self.metric_key:
            raise ValueError("Metric threshold rules require an approved metric key.")
        if self.interface_id and not self.target_id:
            raise ValueError("Interface rules must also identify their target.")
        return self


class SNMPAlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    warning_threshold: float | None = None
    critical_threshold: float | None = None
    evaluation_window: int | None = Field(default=None, ge=1, le=100)
    minimum_samples: int | None = Field(default=None, ge=1, le=100)
    consecutive_breaches: int | None = Field(default=None, ge=1, le=100)
    recovery_samples: int | None = Field(default=None, ge=1, le=100)
    severity: str | None = Field(default=None, pattern=r"^(info|warning|high|critical)$")
    enabled: bool | None = None
    suppress_during_maintenance: bool | None = None
    notification_enabled: bool | None = None


class SNMPAlertRuleRead(SNMPAlertRuleWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    created_at: datetime
    updated_at: datetime


class SNMPAlertEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    rule_id: UUID
    target_id: UUID
    interface_id: UUID | None
    poll_run_id: UUID | None
    metric_key: str
    severity: str
    is_open: bool
    occurrence_count: int
    flapping: bool
    evidence: dict[str, Any]
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None


class SNMPPollRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    target_id: UUID
    started_at: datetime
    completed_at: datetime | None
    status: str
    trigger_type: str
    triggered_by: str | None
    poll_type: str
    requested_oids: int
    successful_oids: int
    failed_oids: int
    duration_ms: int | None
    error_category: str | None
    error_summary: str | None


class SNMPMetricRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    target_id: UUID
    poll_run_id: UUID
    metric_key: str
    oid: str
    interface_index: int | None
    interface_name: str | None
    value_numeric: float | None
    value_text: str | None
    unit: str | None
    quality: str
    quality_reason: str | None = None
    observed_at: datetime


class SNMPInterfaceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    target_id: UUID
    interface_index: int
    name: str | None
    description: str | None
    alias: str | None
    interface_type: str | None
    mac_address: str | None
    admin_status: str | None
    operational_status: str | None
    speed_bps: int | None
    mtu: int | None
    connector_present: bool | None = None
    is_missing: bool = False
    missed_polls: int = 0
    missing_since: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime


class SNMPCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    target_id: UUID
    sys_name: str | None
    sys_descr: str | None
    sys_object_id: str | None
    sys_location: str | None
    vendor_guess: str | None
    device_type_guess: str | None
    profile_id: UUID | None
    confidence_score: float
    evidence: dict[str, Any]
    review_status: str
    matched_device_id: UUID | None
    matched_discovery_id: UUID | None
    created_at: datetime
    updated_at: datetime


class SNMPPage(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int


class SNMPTargetTestRequest(BaseModel):
    include_optional_identity: bool = True
    temporary_timeout_seconds: int | None = Field(default=None, ge=1, le=30)


class SNMPManualPollRequest(BaseModel):
    poll_type: Literal["system", "availability", "interfaces_preview", "custom_profile"]


class SNMPManualPollResponse(BaseModel):
    poll_run_id: UUID
    accepted_poll_type: str
    status: str
    warnings: list[str] = Field(default_factory=list)


class SNMPCollectionRequest(BaseModel):
    groups: list[Literal[
        "availability", "system", "interface_inventory", "interface_performance",
        "device_performance", "all_profile_metrics",
    ]] = Field(min_length=1, max_length=6)

    @field_validator("groups")
    @classmethod
    def unique_groups(cls, value):
        if len(value) != len(set(value)):
            raise ValueError("Collection groups must be unique.")
        return value


class SNMPCandidateAction(BaseModel):
    expected_updated_at: datetime | None = None


class SNMPCandidateLinkRequest(SNMPCandidateAction):
    device_id: UUID


class SNMPCandidateOnboardRequest(SNMPCandidateAction):
    device: dict[str, Any]


class SNMPCandidateEnrichRequest(SNMPCandidateLinkRequest):
    fields: list[str] = Field(min_length=1, max_length=8)
    overwrite: bool = False


class SNMPMatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    snmp_candidate_id: UUID
    candidate_type: str
    candidate_device_id: UUID | None
    candidate_discovery_id: UUID | None
    match_score: float
    match_level: str
    match_status: str
    matching_fields: list[str]
    conflicting_fields: list[str]
    evidence: dict[str, Any]
    recommended_action: str
    created_at: datetime


class SNMPInterfaceChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    interface_id: UUID
    poll_run_id: UUID | None
    change_type: str
    changed_fields: list[str]
    before_values: dict[str, Any]
    after_values: dict[str, Any]
    detected_at: datetime


class SNMPStateChangeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    target_id: UUID
    interface_id: UUID | None
    poll_run_id: UUID | None
    state_type: str
    severity_hint: str
    previous_value: str | None
    current_value: str | None
    evidence: dict[str, Any]
    detected_at: datetime
    acknowledged_at: datetime | None
