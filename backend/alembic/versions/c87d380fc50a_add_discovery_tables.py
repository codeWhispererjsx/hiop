"""Create Discovery foundation tables.

Revision ID: c87d380fc50a
Revises: a71c8d9e4f20
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c87d380fc50a"
down_revision = "a71c8d9e4f20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "discovery_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(9), server_default="pending", nullable=False),
        sa.Column("range_scanned", sa.String(255)),
        sa.Column("hosts_attempted", sa.Integer(), server_default="0", nullable=False),
        sa.Column("hosts_responded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("new_devices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matched_devices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_devices", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration", sa.Float()),
        sa.Column("trigger_type", sa.String(32), nullable=False),
        sa.Column("triggered_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("error_summary", sa.Text()),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'partial', 'failed')",
            name="discovery_run_status",
        ),
        sa.CheckConstraint("hosts_attempted >= 0", name="ck_discovery_runs_hosts_attempted_nonnegative"),
        sa.CheckConstraint("hosts_responded >= 0", name="ck_discovery_runs_hosts_responded_nonnegative"),
        sa.CheckConstraint("new_devices >= 0", name="ck_discovery_runs_new_devices_nonnegative"),
        sa.CheckConstraint("matched_devices >= 0", name="ck_discovery_runs_matched_devices_nonnegative"),
        sa.CheckConstraint("updated_devices >= 0", name="ck_discovery_runs_updated_devices_nonnegative"),
        sa.CheckConstraint("error_count >= 0", name="ck_discovery_runs_error_count_nonnegative"),
        sa.CheckConstraint("duration IS NULL OR duration >= 0", name="ck_discovery_runs_duration_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_runs_started_at", "discovery_runs", ["started_at"])
    op.create_index("ix_discovery_runs_status", "discovery_runs", ["status"])
    op.create_index("ix_discovery_runs_triggered_by", "discovery_runs", ["triggered_by"])

    op.create_table(
        "discovered_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("mac_address", sa.String(17)),
        sa.Column("hostname", sa.String(255)),
        sa.Column("vendor", sa.String(128)),
        sa.Column("operating_system_guess", sa.String(128)),
        sa.Column("device_type_guess", sa.String(64)),
        sa.Column("network_zone_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("network_zones.id", ondelete="SET NULL")),
        sa.Column("subnet", sa.String(45)),
        sa.Column("discovery_method", sa.String(32), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("times_seen", sa.Integer(), server_default="1", nullable=False),
        sa.Column("response_time", sa.Float()),
        sa.Column("status", sa.String(7), server_default="unknown", nullable=False),
        sa.Column("review_status", sa.String(8), server_default="pending", nullable=False),
        sa.Column("confidence_score", sa.Float()),
        sa.Column("approved_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('online', 'offline', 'unknown')", name="discovery_status"),
        sa.CheckConstraint(
            "review_status IN ('pending', 'approved', 'ignored', 'rejected')",
            name="review_status",
        ),
        sa.CheckConstraint("times_seen >= 1", name="ck_discovered_devices_times_seen_positive"),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 100)",
            name="ck_discovered_devices_confidence_score_range",
        ),
        sa.CheckConstraint(
            "response_time IS NULL OR response_time >= 0",
            name="ck_discovered_devices_response_time_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovered_devices_ip_address", "discovered_devices", ["ip_address"])
    op.create_index("ix_discovered_devices_hostname", "discovered_devices", ["hostname"])
    op.create_index("ix_discovered_devices_review_status", "discovered_devices", ["review_status"])
    op.create_index("ix_discovered_devices_status", "discovered_devices", ["status"])
    op.create_index("ix_discovered_devices_last_seen_at", "discovered_devices", ["last_seen_at"])
    op.create_index("ix_discovered_devices_subnet", "discovered_devices", ["subnet"])
    op.create_index(
        "uq_discovered_devices_mac_identity",
        "discovered_devices",
        [sa.text("lower(mac_address)")],
        unique=True,
        postgresql_where=sa.text("mac_address IS NOT NULL"),
    )
    op.create_index(
        "uq_discovered_devices_approved_device_identity",
        "discovered_devices",
        ["approved_device_id"],
        unique=True,
        postgresql_where=sa.text("approved_device_id IS NOT NULL"),
    )
    op.create_index(
        "uq_discovered_devices_ip_hostname_identity",
        "discovered_devices",
        ["ip_address", sa.text("lower(hostname)")],
        unique=True,
        postgresql_where=sa.text(
            "mac_address IS NULL AND approved_device_id IS NULL AND hostname IS NOT NULL"
        ),
    )
    op.create_index(
        "uq_discovered_devices_ip_only_identity",
        "discovered_devices",
        ["ip_address"],
        unique=True,
        postgresql_where=sa.text(
            "mac_address IS NULL AND approved_device_id IS NULL AND hostname IS NULL"
        ),
    )


def downgrade() -> None:
    op.drop_table("discovered_devices")
    op.drop_table("discovery_runs")
