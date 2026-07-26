"""add scheduled topology operations and alert lifecycle

Revision ID: fa6d8e1c4b20
Revises: f2e4a6c8d013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "fa6d8e1c4b20"
down_revision = "f2e4a6c8d013"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("topology_snapshots", sa.Column("is_operational_baseline", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("topology_snapshots", sa.Column("is_protected", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_table(
        "topology_schedule_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("neighbor_collection_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("neighbor_collection_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("inference_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("inference_interval_minutes", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("snapshot_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("snapshot_interval_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("change_evaluation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("change_evaluation_interval_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("protocol_mode", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("dry_run_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maximum_targets_per_run", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("maximum_run_duration", sa.Integer(), nullable=False, server_default="1800"),
        sa.Column("jitter_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("stale_run_timeout_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("missing_link_grace_runs", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("automatic_review_threshold", sa.Integer(), nullable=False, server_default="95"),
        sa.Column("alerting_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("maintenance_reason", sa.String(500)),
        sa.Column("maintenance_started_at", sa.DateTime(timezone=True)),
        sa.Column("maintenance_ends_at", sa.DateTime(timezone=True)),
        sa.Column("maintenance_started_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_scheduler_reconciliation_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("topology_id", name="uq_topology_schedule_topology"),
    )
    op.create_index("ix_topology_schedule_configurations_topology_id", "topology_schedule_configurations", ["topology_id"])
    op.create_table(
        "topology_operational_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_type", sa.String(30), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("target_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("changes_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conflicts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("alerts_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("snapshot_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topology_snapshots.id", ondelete="SET NULL")),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("triggered_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_topology_operational_topology_status_started", "topology_operational_runs", ["topology_id", "status", "started_at"])
    op.create_index("ix_topology_operational_type_started", "topology_operational_runs", ["run_type", "started_at"])
    op.create_table(
        "topology_alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topologies.id", ondelete="CASCADE")),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topology_nodes.id", ondelete="CASCADE")),
        sa.Column("link_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topology_links.id", ondelete="CASCADE")),
        sa.Column("group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topology_groups.id", ondelete="CASCADE")),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("threshold", sa.Integer()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("minimum_confidence", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("consecutive_occurrences", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("recovery_occurrences", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("suppress_during_maintenance", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notification_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("ticket_creation_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_topology_alert_rules_topology_enabled", "topology_alert_rules", ["topology_id", "enabled"])
    op.create_table(
        "topology_alert_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topologies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topology_alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("alert_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flapping", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("suppressed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_topology_alert_open_severity", "topology_alert_events", ["is_open", "severity"])
    op.create_index("ix_topology_alert_topology_seen", "topology_alert_events", ["topology_id", "last_seen_at"])


def downgrade():
    op.drop_table("topology_alert_events")
    op.drop_table("topology_alert_rules")
    op.drop_table("topology_operational_runs")
    op.drop_table("topology_schedule_configurations")
    op.drop_column("topology_snapshots", "is_protected")
    op.drop_column("topology_snapshots", "is_operational_baseline")
