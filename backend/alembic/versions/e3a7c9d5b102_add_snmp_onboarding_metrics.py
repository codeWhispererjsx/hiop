"""add SNMP onboarding, interface history, and operational metric fields

Revision ID: e3a7c9d5b102
Revises: d2f6b8c4a901
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "e3a7c9d5b102"
down_revision = "d2f6b8c4a901"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("snmp_metrics", sa.Column("quality_reason", sa.String(255)))
    op.create_index("ix_snmp_metrics_interface_metric_observed", "snmp_metrics", ["target_id", "interface_index", "metric_key", "observed_at"])
    op.add_column("snmp_interfaces", sa.Column("connector_present", sa.Boolean()))
    op.add_column("snmp_interfaces", sa.Column("is_missing", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("snmp_interfaces", sa.Column("missed_polls", sa.Integer(), server_default="0", nullable=False))
    op.add_column("snmp_interfaces", sa.Column("missing_since", sa.DateTime(timezone=True)))
    op.create_index("ix_snmp_interfaces_target_missing", "snmp_interfaces", ["target_id", "is_missing"])

    op.create_table(
        "snmp_match_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("snmp_candidate_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_discovery_candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_type", sa.String(30), nullable=False),
        sa.Column("candidate_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("candidate_discovery_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovered_devices.id", ondelete="CASCADE")),
        sa.Column("match_score", sa.Float(), nullable=False),
        sa.Column("match_level", sa.String(20), nullable=False),
        sa.Column("match_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("matching_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("conflicting_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("recommended_action", sa.String(20), nullable=False),
        sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("match_score BETWEEN 0 AND 100", name="ck_snmp_match_score"),
        sa.UniqueConstraint("snmp_candidate_id", "candidate_type", "candidate_device_id", "candidate_discovery_id", name="uq_snmp_match_identity"),
    )
    op.create_index("ix_snmp_matches_candidate_score", "snmp_match_candidates", ["snmp_candidate_id", "match_score"])
    op.create_index("ix_snmp_matches_status", "snmp_match_candidates", ["match_status"])

    op.create_table(
        "snmp_device_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_device_profiles.id", ondelete="SET NULL")),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("management_ip", sa.String(45)),
        sa.Column("sys_object_id", sa.String(255)),
        sa.Column("health_status", sa.String(30), server_default="unknown", nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("linked_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("target_id", name="uq_snmp_device_link_target"),
    )
    op.create_index("ix_snmp_device_links_device_id", "snmp_device_links", ["device_id"])
    op.create_index("ix_snmp_device_links_health", "snmp_device_links", ["health_status"])

    op.create_table(
        "snmp_interface_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interface_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_interfaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("poll_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_poll_runs.id", ondelete="SET NULL")),
        sa.Column("change_type", sa.String(30), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("before_values", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("after_values", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_snmp_interface_changes_interface_detected", "snmp_interface_changes", ["interface_id", "detected_at"])

    op.create_table(
        "snmp_state_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_targets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interface_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_interfaces.id", ondelete="CASCADE")),
        sa.Column("poll_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_poll_runs.id", ondelete="SET NULL")),
        sa.Column("state_type", sa.String(40), nullable=False),
        sa.Column("severity_hint", sa.String(20), server_default="info", nullable=False),
        sa.Column("previous_value", sa.String(500)),
        sa.Column("current_value", sa.String(500)),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_snmp_state_target_detected", "snmp_state_changes", ["target_id", "detected_at"])
    op.create_index("ix_snmp_state_interface_detected", "snmp_state_changes", ["interface_id", "detected_at"])
    op.create_index("ix_snmp_state_type", "snmp_state_changes", ["state_type"])


def downgrade():
    op.drop_table("snmp_state_changes")
    op.drop_table("snmp_interface_changes")
    op.drop_table("snmp_device_links")
    op.drop_table("snmp_match_candidates")
    op.drop_index("ix_snmp_interfaces_target_missing", table_name="snmp_interfaces")
    for column in ("missing_since", "missed_polls", "is_missing", "connector_present"):
        op.drop_column("snmp_interfaces", column)
    op.drop_index("ix_snmp_metrics_interface_metric_observed", table_name="snmp_metrics")
    op.drop_column("snmp_metrics", "quality_reason")
