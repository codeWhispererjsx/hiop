"""add SNMP scheduling, maintenance, interface policy, and alert lifecycle

Revision ID: f5e4d3c2b1a0
Revises: e3a7c9d5b102
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f5e4d3c2b1a0"
down_revision = "e3a7c9d5b102"
branch_labels = None
depends_on = None


def upgrade():
    for name, default in (
        ("availability_interval_seconds", "300"), ("system_interval_seconds", "900"),
        ("interface_inventory_interval_seconds", "3600"), ("interface_performance_interval_seconds", "300"),
        ("device_performance_interval_seconds", "600"), ("jitter_seconds", "30"),
        ("failure_threshold", "3"), ("recovery_threshold", "2"),
    ):
        op.add_column("snmp_polling_configurations", sa.Column(name, sa.Integer(), nullable=False, server_default=default))
    op.add_column("snmp_polling_configurations", sa.Column("maintenance_mode", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("snmp_polling_configurations", sa.Column("maintenance_reason", sa.String(500)))
    op.add_column("snmp_polling_configurations", sa.Column("maintenance_started_at", sa.DateTime(timezone=True)))
    op.add_column("snmp_polling_configurations", sa.Column("maintenance_ends_at", sa.DateTime(timezone=True)))
    op.add_column("snmp_polling_configurations", sa.Column("maintenance_started_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")))
    op.add_column("snmp_polling_configurations", sa.Column("last_scheduler_reconciliation_at", sa.DateTime(timezone=True)))
    for name, default in (
        ("monitored", sa.true()), ("critical", sa.false()), ("alert_on_down", sa.false()),
        ("alert_on_utilization", sa.false()), ("alert_on_errors", sa.false()),
    ):
        op.add_column("snmp_interfaces", sa.Column(name, sa.Boolean(), nullable=False, server_default=default))
    op.add_column("snmp_interfaces", sa.Column("utilization_warning", sa.Float()))
    op.add_column("snmp_interfaces", sa.Column("utilization_critical", sa.Float()))
    op.add_column("snmp_interfaces", sa.Column("monitoring_notes", sa.String(500)))
    op.create_table(
        "snmp_alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("rule_type", sa.String(50), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_targets.id", ondelete="CASCADE")),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_device_profiles.id", ondelete="CASCADE")),
        sa.Column("interface_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_interfaces.id", ondelete="CASCADE")),
        sa.Column("metric_key", sa.String(120)),
        sa.Column("comparison_operator", sa.String(40), nullable=False),
        sa.Column("warning_threshold", sa.Float()),
        sa.Column("critical_threshold", sa.Float()),
        sa.Column("evaluation_window", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("minimum_samples", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("consecutive_breaches", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("recovery_samples", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("suppress_during_maintenance", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notification_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("comparison_operator IN ('greater_than','greater_than_or_equal','less_than','less_than_or_equal','equal','not_equal','state_changed','missing','stale')", name="ck_snmp_alert_rule_operator"),
        sa.CheckConstraint("severity IN ('info','warning','high','critical')", name="ck_snmp_alert_rule_severity"),
    )
    op.create_index("ix_snmp_alert_rules_target_enabled", "snmp_alert_rules", ["target_id", "enabled"])
    op.create_index("ix_snmp_alert_rules_profile_enabled", "snmp_alert_rules", ["profile_id", "enabled"])
    op.create_table(
        "snmp_alert_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_alert_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interface_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_interfaces.id", ondelete="CASCADE")),
        sa.Column("poll_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_poll_runs.id", ondelete="SET NULL")),
        sa.Column("metric_key", sa.String(120), nullable=False, server_default=""),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("breach_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flapping", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("recovery_evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_snmp_alert_events_open_severity", "snmp_alert_events", ["is_open", "severity"])
    op.create_index("ix_snmp_alert_events_target_last_seen", "snmp_alert_events", ["target_id", "last_seen_at"])


def downgrade():
    op.drop_table("snmp_alert_events")
    op.drop_table("snmp_alert_rules")
    for name in ("monitoring_notes", "utilization_critical", "utilization_warning", "alert_on_errors", "alert_on_utilization", "alert_on_down", "critical", "monitored"):
        op.drop_column("snmp_interfaces", name)
    for name in ("last_scheduler_reconciliation_at", "maintenance_started_by", "maintenance_ends_at", "maintenance_started_at", "maintenance_reason", "maintenance_mode", "recovery_threshold", "failure_threshold", "jitter_seconds", "device_performance_interval_seconds", "interface_performance_interval_seconds", "interface_inventory_interval_seconds", "system_interval_seconds", "availability_interval_seconds"):
        op.drop_column("snmp_polling_configurations", name)
