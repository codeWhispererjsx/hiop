"""Add non-live SNMP integration foundation.

Revision ID: c9e4a7b2d610
Revises: b8d4f6a10235
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c9e4a7b2d610"
down_revision = "b8d4f6a10235"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB(astext_type=sa.Text())


def timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "snmp_credentials",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("version", sa.String(8), nullable=False),
        sa.Column("community_encrypted", sa.Text()),
        sa.Column("username", sa.String(128)),
        sa.Column("authentication_protocol", sa.String(16), server_default="none", nullable=False),
        sa.Column("authentication_secret_encrypted", sa.Text()),
        sa.Column("privacy_protocol", sa.String(16), server_default="none", nullable=False),
        sa.Column("privacy_secret_encrypted", sa.Text()),
        sa.Column("security_level", sa.String(20), server_default="noAuthNoPriv", nullable=False),
        sa.Column("context_name", sa.String(128)),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *timestamps(),
        sa.CheckConstraint("version IN ('v1','v2c','v3')", name="ck_snmp_credential_version"),
        sa.CheckConstraint("security_level IN ('noAuthNoPriv','authNoPriv','authPriv')", name="ck_snmp_credential_security_level"),
    )
    op.create_index("ix_snmp_credentials_enabled", "snmp_credentials", ["enabled"])

    op.create_table(
        "snmp_device_profiles",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("vendor", sa.String(120)),
        sa.Column("device_type", sa.String(40), nullable=False),
        sa.Column("sys_object_id_pattern", sa.String(255)),
        sa.Column("sys_descr_pattern", sa.String(255)),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("profile_data", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("name", name="uq_snmp_profile_name"),
        sa.UniqueConstraint("vendor", "device_type", "priority", name="uq_snmp_profile_vendor_type_priority"),
    )
    op.create_index("ix_snmp_profiles_sys_object_id_pattern", "snmp_device_profiles", ["sys_object_id_pattern"])
    op.create_index("ix_snmp_profiles_enabled_priority", "snmp_device_profiles", ["enabled", "priority"])

    op.create_table(
        "snmp_targets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("device_id", UUID, sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("discovered_device_id", UUID, sa.ForeignKey("discovered_devices.id", ondelete="SET NULL")),
        sa.Column("credential_id", UUID, sa.ForeignKey("snmp_credentials.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("hostname", sa.String(255)),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("port", sa.Integer(), server_default="161", nullable=False),
        sa.Column("version", sa.String(8), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("polling_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), server_default="5", nullable=False),
        sa.Column("retries", sa.Integer(), server_default="1", nullable=False),
        sa.Column("transport", sa.String(8), server_default="udp", nullable=False),
        sa.Column("context_name", sa.String(128), server_default="", nullable=False),
        sa.Column("network_zone_id", UUID, sa.ForeignKey("network_zones.id", ondelete="SET NULL")),
        sa.Column("location_id", UUID, sa.ForeignKey("rooms.id", ondelete="SET NULL")),
        sa.Column("last_tested_at", sa.DateTime(timezone=True)),
        sa.Column("last_test_status", sa.String(30)),
        sa.Column("last_test_message", sa.String(500)),
        sa.Column("last_successful_poll_at", sa.DateTime(timezone=True)),
        sa.Column("last_failed_poll_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        *timestamps(),
        sa.UniqueConstraint("ip_address", "port", "transport", "context_name", name="uq_snmp_target_endpoint_context"),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_snmp_target_port"),
        sa.CheckConstraint("timeout_seconds BETWEEN 1 AND 60", name="ck_snmp_target_timeout"),
        sa.CheckConstraint("retries BETWEEN 0 AND 10", name="ck_snmp_target_retries"),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_snmp_target_failures"),
    )
    for name, columns in (
        ("ix_snmp_targets_ip_address", ["ip_address"]),
        ("ix_snmp_targets_hostname", ["hostname"]),
        ("ix_snmp_targets_credential_id", ["credential_id"]),
        ("ix_snmp_targets_device_id", ["device_id"]),
        ("ix_snmp_targets_discovered_device_id", ["discovered_device_id"]),
        ("ix_snmp_targets_last_test_status", ["last_test_status"]),
        ("ix_snmp_targets_last_successful_poll_at", ["last_successful_poll_at"]),
        ("ix_snmp_targets_enabled", ["enabled"]),
    ): op.create_index(name, "snmp_targets", columns)

    op.create_table(
        "snmp_oid_definitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("oid", sa.String(255), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("data_type", sa.String(20), nullable=False),
        sa.Column("unit", sa.String(40)),
        sa.Column("scale_factor", sa.Float(), server_default="1", nullable=False),
        sa.Column("collection_type", sa.String(20), nullable=False),
        sa.Column("profile_id", UUID, sa.ForeignKey("snmp_device_profiles.id", ondelete="CASCADE")),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("criticality", sa.String(20), server_default="normal", nullable=False),
        sa.Column("transform_type", sa.String(30), server_default="identity", nullable=False),
        *timestamps(),
        sa.UniqueConstraint("profile_id", "metric_key", "oid", name="uq_snmp_oid_profile_metric"),
        sa.CheckConstraint("scale_factor > 0", name="ck_snmp_oid_scale_positive"),
    )
    op.create_index("ix_snmp_oids_metric_key", "snmp_oid_definitions", ["metric_key"])
    op.create_index("ix_snmp_oids_oid", "snmp_oid_definitions", ["oid"])

    op.create_table(
        "snmp_polling_configurations",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("target_id", UUID, sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("polling_interval_seconds", sa.Integer(), server_default="300", nullable=False),
        sa.Column("availability_poll_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("system_poll_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("interface_poll_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("performance_poll_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("inventory_poll_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("alerting_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("profile_id", UUID, sa.ForeignKey("snmp_device_profiles.id", ondelete="SET NULL")),
        sa.Column("max_oids_per_poll", sa.Integer(), server_default="50", nullable=False),
        sa.Column("max_interfaces", sa.Integer(), server_default="256", nullable=False),
        sa.Column("stale_after_seconds", sa.Integer(), server_default="900", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("polling_interval_seconds BETWEEN 30 AND 86400", name="ck_snmp_poll_config_interval"),
        sa.CheckConstraint("max_oids_per_poll BETWEEN 1 AND 1000", name="ck_snmp_poll_config_oids"),
        sa.CheckConstraint("max_interfaces BETWEEN 1 AND 10000", name="ck_snmp_poll_config_interfaces"),
    )

    op.create_table(
        "snmp_poll_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("target_id", UUID, sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("trigger_type", sa.String(20), server_default="manual", nullable=False),
        sa.Column("triggered_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("poll_type", sa.String(20), nullable=False),
        sa.Column("requested_oids", sa.Integer(), server_default="0", nullable=False),
        sa.Column("successful_oids", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_oids", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_category", sa.String(30)),
        sa.Column("error_summary", sa.String(500)),
        *timestamps(),
        sa.CheckConstraint("status IN ('pending','running','completed','partial','failed','cancelled')", name="ck_snmp_poll_run_status"),
        sa.CheckConstraint("requested_oids >= 0 AND successful_oids >= 0 AND failed_oids >= 0", name="ck_snmp_poll_run_counts"),
    )
    op.create_index("ix_snmp_poll_runs_target_id", "snmp_poll_runs", ["target_id"])
    op.create_index("ix_snmp_poll_runs_status", "snmp_poll_runs", ["status"])
    op.create_index("ix_snmp_poll_runs_started_at", "snmp_poll_runs", ["started_at"])

    op.create_table(
        "snmp_metrics",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("target_id", UUID, sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("poll_run_id", UUID, sa.ForeignKey("snmp_poll_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("oid", sa.String(255), nullable=False),
        sa.Column("interface_index", sa.Integer()),
        sa.Column("interface_name", sa.String(255)),
        sa.Column("value_numeric", sa.Numeric(30, 8)),
        sa.Column("value_text", sa.String(1000)),
        sa.Column("unit", sa.String(40)),
        sa.Column("quality", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("value_numeric IS NOT NULL OR value_text IS NOT NULL", name="ck_snmp_metric_has_value"),
    )
    op.create_index("ix_snmp_metrics_target_metric_observed", "snmp_metrics", ["target_id", "metric_key", "observed_at"])
    op.create_index("ix_snmp_metrics_poll_run_id", "snmp_metrics", ["poll_run_id"])
    op.create_index("ix_snmp_metrics_observed_at", "snmp_metrics", ["observed_at"])

    op.create_table(
        "snmp_interfaces",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("target_id", UUID, sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interface_index", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255)), sa.Column("description", sa.String(500)),
        sa.Column("alias", sa.String(255)), sa.Column("interface_type", sa.String(80)),
        sa.Column("mac_address", sa.String(17)), sa.Column("admin_status", sa.String(20)),
        sa.Column("operational_status", sa.String(20)), sa.Column("speed_bps", sa.BigInteger()),
        sa.Column("mtu", sa.Integer()), sa.Column("last_change", sa.BigInteger()),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("target_id", "interface_index", name="uq_snmp_interface_target_index"),
    )
    op.create_index("ix_snmp_interfaces_target_id", "snmp_interfaces", ["target_id"])
    op.create_index("ix_snmp_interfaces_interface_index", "snmp_interfaces", ["interface_index"])
    op.create_index("ix_snmp_interfaces_last_seen_at", "snmp_interfaces", ["last_seen_at"])

    op.create_table(
        "snmp_discovery_candidates",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("target_id", UUID, sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sys_name", sa.String(255)), sa.Column("sys_descr", sa.String(1000)),
        sa.Column("sys_object_id", sa.String(255)), sa.Column("sys_location", sa.String(255)),
        sa.Column("sys_contact", sa.String(255)), sa.Column("vendor_guess", sa.String(120)),
        sa.Column("device_type_guess", sa.String(40)),
        sa.Column("profile_id", UUID, sa.ForeignKey("snmp_device_profiles.id", ondelete="SET NULL")),
        sa.Column("confidence_score", sa.Float(), server_default="0", nullable=False),
        sa.Column("evidence", JSON, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("review_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("matched_device_id", UUID, sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("matched_discovery_id", UUID, sa.ForeignKey("discovered_devices.id", ondelete="SET NULL")),
        sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_snmp_candidate_confidence"),
    )
    op.create_index("ix_snmp_candidates_target_id", "snmp_discovery_candidates", ["target_id"])
    op.create_index("ix_snmp_candidates_sys_object_id", "snmp_discovery_candidates", ["sys_object_id"])
    op.create_index("ix_snmp_candidates_review_status", "snmp_discovery_candidates", ["review_status"])


def downgrade() -> None:
    for table in (
        "snmp_discovery_candidates", "snmp_interfaces", "snmp_metrics",
        "snmp_poll_runs", "snmp_polling_configurations", "snmp_oid_definitions",
        "snmp_targets", "snmp_device_profiles", "snmp_credentials",
    ):
        op.drop_table(table)
