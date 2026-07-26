"""Persistence foundation for SNMP configuration and future observations.

This module intentionally contains no transport or polling implementation.
"""
import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    BigInteger, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SNMPVersion(str, enum.Enum):
    V1 = "v1"
    V2C = "v2c"
    V3 = "v3"


class SNMPSecurityLevel(str, enum.Enum):
    NO_AUTH_NO_PRIV = "noAuthNoPriv"
    AUTH_NO_PRIV = "authNoPriv"
    AUTH_PRIV = "authPriv"


class SNMPAuthProtocol(str, enum.Enum):
    NONE = "none"
    MD5 = "MD5"
    SHA = "SHA"
    SHA224 = "SHA224"
    SHA256 = "SHA256"
    SHA384 = "SHA384"
    SHA512 = "SHA512"


class SNMPPrivacyProtocol(str, enum.Enum):
    NONE = "none"
    DES = "DES"
    AES128 = "AES128"
    AES192 = "AES192"
    AES256 = "AES256"


class SNMPPollStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SNMPPollType(str, enum.Enum):
    AVAILABILITY = "availability"
    SYSTEM = "system"
    INTERFACE = "interface"
    PERFORMANCE = "performance"
    INVENTORY = "inventory"
    COMPOSITE = "composite"


class SNMPMetricQuality(str, enum.Enum):
    GOOD = "good"
    WARNING = "warning"
    MISSING = "missing"
    INVALID = "invalid"
    STALE = "stale"
    TRUNCATED = "truncated"
    RESET = "reset"
    WRAPPED = "wrapped"
    UNSUPPORTED = "unsupported"


class SNMPDataType(str, enum.Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    COUNTER = "counter"
    GAUGE = "gauge"
    TIMETICKS = "timeticks"
    ENUM = "enum"


class SNMPCollectionType(str, enum.Enum):
    SCALAR = "scalar"
    TABLE = "table"
    COUNTER = "counter"
    GAUGE = "gauge"
    TIMETICKS = "timeticks"
    STRING = "string"
    INTEGER = "integer"
    ENUM = "enum"


class SNMPTransport(str, enum.Enum):
    UDP = "udp"


class SNMPReviewStatus(str, enum.Enum):
    PENDING = "pending"
    MATCHED = "matched"
    APPROVED = "approved"
    IGNORED = "ignored"
    CONFLICT = "conflict"


class SNMPDeviceType(str, enum.Enum):
    SWITCH = "switch"
    ROUTER = "router"
    FIREWALL = "firewall"
    ACCESS_POINT = "access_point"
    WIRELESS_CONTROLLER = "wireless_controller"
    PRINTER = "printer"
    UPS = "ups"
    SERVER_MANAGEMENT = "server_management_interface"
    ENVIRONMENTAL_SENSOR = "environmental_sensor"
    IP_PHONE_SYSTEM = "ip_phone_system"
    GENERIC = "generic_snmp_device"


class SNMPErrorCategory(str, enum.Enum):
    HOST_UNREACHABLE = "host_unreachable"
    TIMEOUT = "timeout"
    TRANSPORT_ERROR = "transport_error"
    UNAUTHORIZED_TARGET = "unauthorized_target"
    CREDENTIAL_MISSING = "credential_missing"
    AUTHENTICATION_FAILED = "authentication_failed"
    PRIVACY_FAILED = "privacy_failed"
    UNSUPPORTED_VERSION = "unsupported_version"
    UNSUPPORTED_PROTOCOL = "unsupported_protocol"
    MALFORMED_RESPONSE = "malformed_response"
    OID_NOT_FOUND = "oid_not_found"
    ACCESS_DENIED = "access_denied"
    TOO_BIG = "too_big"
    WALK_LIMIT_EXCEEDED = "walk_limit_exceeded"
    CANCELLED = "cancelled"
    CONFIGURATION_ERROR = "configuration_error"
    DECRYPTION_FAILED = "decryption_failed"
    UNKNOWN_ERROR = "unknown_error"


class SNMPCredential(Base):
    __tablename__ = "snmp_credentials"
    __table_args__ = (
        CheckConstraint("version IN ('v1','v2c','v3')", name="ck_snmp_credential_version"),
        CheckConstraint(
            "security_level IN ('noAuthNoPriv','authNoPriv','authPriv')",
            name="ck_snmp_credential_security_level",
        ),
        Index("ix_snmp_credentials_enabled", "enabled"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    version: Mapped[str] = mapped_column(String(8), nullable=False)
    community_encrypted: Mapped[str | None] = mapped_column(Text)
    username: Mapped[str | None] = mapped_column(String(128))
    authentication_protocol: Mapped[str] = mapped_column(String(16), default="none", server_default="none", nullable=False)
    authentication_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    privacy_protocol: Mapped[str] = mapped_column(String(16), default="none", server_default="none", nullable=False)
    privacy_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    security_level: Mapped[str] = mapped_column(String(20), default="noAuthNoPriv", server_default="noAuthNoPriv", nullable=False)
    context_name: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    targets: Mapped[list["SNMPTarget"]] = relationship(back_populates="credential")


class SNMPDeviceProfile(Base):
    __tablename__ = "snmp_device_profiles"
    __table_args__ = (
        UniqueConstraint("name", name="uq_snmp_profile_name"),
        UniqueConstraint("vendor", "device_type", "priority", name="uq_snmp_profile_vendor_type_priority"),
        Index("ix_snmp_profiles_sys_object_id_pattern", "sys_object_id_pattern"),
        Index("ix_snmp_profiles_enabled_priority", "enabled", "priority"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    vendor: Mapped[str | None] = mapped_column(String(120))
    device_type: Mapped[str] = mapped_column(String(40), default=SNMPDeviceType.GENERIC.value, nullable=False)
    sys_object_id_pattern: Mapped[str | None] = mapped_column(String(255))
    sys_descr_pattern: Mapped[str | None] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, server_default="100", nullable=False)
    profile_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    oid_definitions: Mapped[list["SNMPOIDDefinition"]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class SNMPTarget(Base):
    __tablename__ = "snmp_targets"
    __table_args__ = (
        UniqueConstraint("ip_address", "port", "transport", "context_name", name="uq_snmp_target_endpoint_context"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_snmp_target_port"),
        CheckConstraint("timeout_seconds BETWEEN 1 AND 60", name="ck_snmp_target_timeout"),
        CheckConstraint("retries BETWEEN 0 AND 10", name="ck_snmp_target_retries"),
        CheckConstraint("consecutive_failures >= 0", name="ck_snmp_target_failures"),
        Index("ix_snmp_targets_ip_address", "ip_address"),
        Index("ix_snmp_targets_hostname", "hostname"),
        Index("ix_snmp_targets_credential_id", "credential_id"),
        Index("ix_snmp_targets_device_id", "device_id"),
        Index("ix_snmp_targets_discovered_device_id", "discovered_device_id"),
        Index("ix_snmp_targets_last_test_status", "last_test_status"),
        Index("ix_snmp_targets_last_successful_poll_at", "last_successful_poll_at"),
        Index("ix_snmp_targets_enabled", "enabled"),
        Index("ix_snmp_targets_detected_profile_id", "detected_profile_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    discovered_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id", ondelete="SET NULL"))
    credential_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_credentials.id", ondelete="RESTRICT"), nullable=False)
    hostname: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=161, server_default="161", nullable=False)
    version: Mapped[str] = mapped_column(String(8), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    polling_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    retries: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    transport: Mapped[str] = mapped_column(String(8), default="udp", server_default="udp", nullable=False)
    context_name: Mapped[str] = mapped_column(String(128), default="", server_default="", nullable=False)
    network_zone_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("network_zones.id", ondelete="SET NULL"))
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="SET NULL"))
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_status: Mapped[str | None] = mapped_column(String(30))
    last_test_message: Mapped[str | None] = mapped_column(String(500))
    last_successful_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failed_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    last_response_time_ms: Mapped[float | None] = mapped_column(Float)
    detected_sys_object_id: Mapped[str | None] = mapped_column(String(255))
    detected_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_device_profiles.id", ondelete="SET NULL"))
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    credential: Mapped[SNMPCredential] = relationship(back_populates="targets")
    polling_configuration: Mapped["SNMPPollingConfiguration | None"] = relationship(back_populates="target", uselist=False, cascade="all, delete-orphan")
    poll_runs: Mapped[list["SNMPPollRun"]] = relationship(back_populates="target", cascade="all, delete-orphan")
    interfaces: Mapped[list["SNMPInterface"]] = relationship(back_populates="target", cascade="all, delete-orphan")
    candidates: Mapped[list["SNMPDiscoveryCandidate"]] = relationship(back_populates="target", cascade="all, delete-orphan")


class SNMPOIDDefinition(Base):
    __tablename__ = "snmp_oid_definitions"
    __table_args__ = (
        UniqueConstraint("profile_id", "metric_key", "oid", name="uq_snmp_oid_profile_metric"),
        CheckConstraint("scale_factor > 0", name="ck_snmp_oid_scale_positive"),
        Index("ix_snmp_oids_metric_key", "metric_key"),
        Index("ix_snmp_oids_oid", "oid"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    oid: Mapped[str] = mapped_column(String(255), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    scale_factor: Mapped[float] = mapped_column(Float, default=1.0, server_default="1", nullable=False)
    collection_type: Mapped[str] = mapped_column(String(20), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_device_profiles.id", ondelete="CASCADE"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    criticality: Mapped[str] = mapped_column(String(20), default="normal", server_default="normal", nullable=False)
    transform_type: Mapped[str] = mapped_column(String(30), default="identity", server_default="identity", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    profile: Mapped[SNMPDeviceProfile | None] = relationship(back_populates="oid_definitions")


class SNMPPollingConfiguration(Base):
    __tablename__ = "snmp_polling_configurations"
    __table_args__ = (
        CheckConstraint("polling_interval_seconds BETWEEN 30 AND 86400", name="ck_snmp_poll_config_interval"),
        CheckConstraint("max_oids_per_poll BETWEEN 1 AND 1000", name="ck_snmp_poll_config_oids"),
        CheckConstraint("max_interfaces BETWEEN 1 AND 10000", name="ck_snmp_poll_config_interfaces"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), unique=True, nullable=False)
    polling_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="300", nullable=False)
    availability_poll_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    system_poll_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    interface_poll_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    performance_poll_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    inventory_poll_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    alerting_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_device_profiles.id", ondelete="SET NULL"))
    max_oids_per_poll: Mapped[int] = mapped_column(Integer, default=50, server_default="50", nullable=False)
    max_interfaces: Mapped[int] = mapped_column(Integer, default=256, server_default="256", nullable=False)
    stale_after_seconds: Mapped[int] = mapped_column(Integer, default=900, server_default="900", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    availability_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="300", nullable=False)
    system_interval_seconds: Mapped[int] = mapped_column(Integer, default=900, server_default="900", nullable=False)
    interface_inventory_interval_seconds: Mapped[int] = mapped_column(Integer, default=3600, server_default="3600", nullable=False)
    interface_performance_interval_seconds: Mapped[int] = mapped_column(Integer, default=300, server_default="300", nullable=False)
    device_performance_interval_seconds: Mapped[int] = mapped_column(Integer, default=600, server_default="600", nullable=False)
    jitter_seconds: Mapped[int] = mapped_column(Integer, default=30, server_default="30", nullable=False)
    failure_threshold: Mapped[int] = mapped_column(Integer, default=3, server_default="3", nullable=False)
    recovery_threshold: Mapped[int] = mapped_column(Integer, default=2, server_default="2", nullable=False)
    maintenance_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    maintenance_reason: Mapped[str | None] = mapped_column(String(500))
    maintenance_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    maintenance_started_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    last_scheduler_reconciliation_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    target: Mapped[SNMPTarget] = relationship(back_populates="polling_configuration")


class SNMPPollRun(Base):
    __tablename__ = "snmp_poll_runs"
    __table_args__ = (
        CheckConstraint("status IN ('pending','running','completed','partial','failed','cancelled')", name="ck_snmp_poll_run_status"),
        CheckConstraint("requested_oids >= 0 AND successful_oids >= 0 AND failed_oids >= 0", name="ck_snmp_poll_run_counts"),
        Index("ix_snmp_poll_runs_target_id", "target_id"),
        Index("ix_snmp_poll_runs_status", "status"),
        Index("ix_snmp_poll_runs_started_at", "started_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), default="manual", server_default="manual", nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    poll_type: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_oids: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    successful_oids: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    failed_oids: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_category: Mapped[str | None] = mapped_column(String(30))
    error_summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    target: Mapped[SNMPTarget] = relationship(back_populates="poll_runs")
    metrics: Mapped[list["SNMPMetric"]] = relationship(back_populates="poll_run", cascade="all, delete-orphan")


class SNMPMetric(Base):
    __tablename__ = "snmp_metrics"
    __table_args__ = (
        CheckConstraint("value_numeric IS NOT NULL OR value_text IS NOT NULL", name="ck_snmp_metric_has_value"),
        Index("ix_snmp_metrics_target_metric_observed", "target_id", "metric_key", "observed_at"),
        Index("ix_snmp_metrics_poll_run_id", "poll_run_id"),
        Index("ix_snmp_metrics_observed_at", "observed_at"),
        Index("ix_snmp_metrics_interface_metric_observed", "target_id", "interface_index", "metric_key", "observed_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    poll_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_poll_runs.id", ondelete="CASCADE"), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(120), nullable=False)
    oid: Mapped[str] = mapped_column(String(255), nullable=False)
    interface_index: Mapped[int | None] = mapped_column(Integer)
    interface_name: Mapped[str | None] = mapped_column(String(255))
    value_numeric: Mapped[float | None] = mapped_column(Numeric(30, 8))
    value_text: Mapped[str | None] = mapped_column(String(1000))
    unit: Mapped[str | None] = mapped_column(String(40))
    quality: Mapped[str] = mapped_column(String(20), default="warning", server_default="warning", nullable=False)
    quality_reason: Mapped[str | None] = mapped_column(String(255))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    poll_run: Mapped[SNMPPollRun] = relationship(back_populates="metrics")


class SNMPInterface(Base):
    __tablename__ = "snmp_interfaces"
    __table_args__ = (
        UniqueConstraint("target_id", "interface_index", name="uq_snmp_interface_target_index"),
        Index("ix_snmp_interfaces_target_id", "target_id"),
        Index("ix_snmp_interfaces_interface_index", "interface_index"),
        Index("ix_snmp_interfaces_last_seen_at", "last_seen_at"),
        Index("ix_snmp_interfaces_target_missing", "target_id", "is_missing"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    interface_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(500))
    alias: Mapped[str | None] = mapped_column(String(255))
    interface_type: Mapped[str | None] = mapped_column(String(80))
    mac_address: Mapped[str | None] = mapped_column(String(17))
    admin_status: Mapped[str | None] = mapped_column(String(20))
    operational_status: Mapped[str | None] = mapped_column(String(20))
    speed_bps: Mapped[int | None] = mapped_column(BigInteger)
    mtu: Mapped[int | None] = mapped_column(Integer)
    last_change: Mapped[int | None] = mapped_column(BigInteger)
    connector_present: Mapped[bool | None] = mapped_column(Boolean)
    is_missing: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    missed_polls: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    monitored: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    critical: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    alert_on_down: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    alert_on_utilization: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    utilization_warning: Mapped[float | None] = mapped_column(Float)
    utilization_critical: Mapped[float | None] = mapped_column(Float)
    alert_on_errors: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    monitoring_notes: Mapped[str | None] = mapped_column(String(500))
    missing_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    target: Mapped[SNMPTarget] = relationship(back_populates="interfaces")
    changes: Mapped[list["SNMPInterfaceChange"]] = relationship(back_populates="interface", cascade="all, delete-orphan")


class SNMPDiscoveryCandidate(Base):
    __tablename__ = "snmp_discovery_candidates"
    __table_args__ = (
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_snmp_candidate_confidence"),
        Index("ix_snmp_candidates_target_id", "target_id"),
        Index("ix_snmp_candidates_sys_object_id", "sys_object_id"),
        Index("ix_snmp_candidates_review_status", "review_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    sys_name: Mapped[str | None] = mapped_column(String(255))
    sys_descr: Mapped[str | None] = mapped_column(String(1000))
    sys_object_id: Mapped[str | None] = mapped_column(String(255))
    sys_location: Mapped[str | None] = mapped_column(String(255))
    sys_contact: Mapped[str | None] = mapped_column(String(255))
    vendor_guess: Mapped[str | None] = mapped_column(String(120))
    device_type_guess: Mapped[str | None] = mapped_column(String(40))
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_device_profiles.id", ondelete="SET NULL"))
    confidence_score: Mapped[float] = mapped_column(Float, default=0, server_default="0", nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
    review_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    matched_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    matched_discovery_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id", ondelete="SET NULL"))
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    target: Mapped[SNMPTarget] = relationship(back_populates="candidates")
    matches: Mapped[list["SNMPMatchCandidate"]] = relationship(back_populates="candidate", cascade="all, delete-orphan")


class SNMPMatchCandidate(Base):
    __tablename__ = "snmp_match_candidates"
    __table_args__ = (
        CheckConstraint("match_score BETWEEN 0 AND 100", name="ck_snmp_match_score"),
        UniqueConstraint("snmp_candidate_id", "candidate_type", "candidate_device_id", "candidate_discovery_id", name="uq_snmp_match_identity"),
        Index("ix_snmp_matches_candidate_score", "snmp_candidate_id", "match_score"),
        Index("ix_snmp_matches_status", "match_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    snmp_candidate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_discovery_candidates.id", ondelete="CASCADE"), nullable=False)
    candidate_type: Mapped[str] = mapped_column(String(30), nullable=False)
    candidate_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"))
    candidate_discovery_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id", ondelete="CASCADE"))
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    match_level: Mapped[str] = mapped_column(String(20), nullable=False)
    match_status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending", nullable=False)
    matching_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=func.text("'[]'::jsonb"), nullable=False)
    conflicting_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=func.text("'[]'::jsonb"), nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    candidate: Mapped[SNMPDiscoveryCandidate] = relationship(back_populates="matches")


class SNMPDeviceLink(Base):
    __tablename__ = "snmp_device_links"
    __table_args__ = (
        UniqueConstraint("target_id", name="uq_snmp_device_link_target"),
        Index("ix_snmp_device_links_device_id", "device_id"),
        Index("ix_snmp_device_links_health", "health_status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_device_profiles.id", ondelete="SET NULL"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    management_ip: Mapped[str | None] = mapped_column(String(45))
    sys_object_id: Mapped[str | None] = mapped_column(String(255))
    health_status: Mapped[str] = mapped_column(String(30), default="unknown", server_default="unknown", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SNMPInterfaceChange(Base):
    __tablename__ = "snmp_interface_changes"
    __table_args__ = (
        Index("ix_snmp_interface_changes_interface_detected", "interface_id", "detected_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    interface_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="CASCADE"), nullable=False)
    poll_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_poll_runs.id", ondelete="SET NULL"))
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_fields: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=func.text("'[]'::jsonb"), nullable=False)
    before_values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
    after_values: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    interface: Mapped[SNMPInterface] = relationship(back_populates="changes")


class SNMPStateChange(Base):
    __tablename__ = "snmp_state_changes"
    __table_args__ = (
        Index("ix_snmp_state_target_detected", "target_id", "detected_at"),
        Index("ix_snmp_state_interface_detected", "interface_id", "detected_at"),
        Index("ix_snmp_state_type", "state_type"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    interface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="CASCADE"))
    poll_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_poll_runs.id", ondelete="SET NULL"))
    state_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity_hint: Mapped[str] = mapped_column(String(20), default="info", server_default="info", nullable=False)
    previous_value: Mapped[str | None] = mapped_column(String(500))
    current_value: Mapped[str | None] = mapped_column(String(500))
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SNMPAlertRule(Base):
    __tablename__ = "snmp_alert_rules"
    __table_args__ = (
        CheckConstraint("comparison_operator IN ('greater_than','greater_than_or_equal','less_than','less_than_or_equal','equal','not_equal','state_changed','missing','stale')", name="ck_snmp_alert_rule_operator"),
        CheckConstraint("severity IN ('info','warning','high','critical')", name="ck_snmp_alert_rule_severity"),
        Index("ix_snmp_alert_rules_target_enabled", "target_id", "enabled"),
        Index("ix_snmp_alert_rules_profile_enabled", "profile_id", "enabled"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_device_profiles.id", ondelete="CASCADE"))
    interface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="CASCADE"))
    metric_key: Mapped[str | None] = mapped_column(String(120))
    comparison_operator: Mapped[str] = mapped_column(String(40), nullable=False)
    warning_threshold: Mapped[float | None] = mapped_column(Float)
    critical_threshold: Mapped[float | None] = mapped_column(Float)
    evaluation_window: Mapped[int] = mapped_column(Integer, default=5, server_default="5", nullable=False)
    minimum_samples: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    consecutive_breaches: Mapped[int] = mapped_column(Integer, default=2, server_default="2", nullable=False)
    recovery_samples: Mapped[int] = mapped_column(Integer, default=2, server_default="2", nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="warning", server_default="warning", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    suppress_during_maintenance: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SNMPAlertEvent(Base):
    __tablename__ = "snmp_alert_events"
    __table_args__ = (
        Index("ix_snmp_alert_events_open_severity", "is_open", "severity"),
        Index("ix_snmp_alert_events_target_last_seen", "target_id", "last_seen_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_alert_rules.id", ondelete="CASCADE"), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False)
    interface_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_interfaces.id", ondelete="CASCADE"))
    poll_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("snmp_poll_runs.id", ondelete="SET NULL"))
    metric_key: Mapped[str] = mapped_column(String(120), default="", server_default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    breach_count: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    recovery_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    flapping: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recovery_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=func.text("'{}'::jsonb"), nullable=False)
