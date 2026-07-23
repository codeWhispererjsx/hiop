"""Add Active Directory integration foundation tables, constraints, and indexes.

Revision ID: e8a9b0c1d2e3
Revises: d4f2a7c8e901
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e8a9b0c1d2e3"
down_revision = "d4f2a7c8e901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. active_directory_connections
    op.create_table(
        "active_directory_connections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("domain_name", sa.String(length=255), nullable=False),
        sa.Column("server_host", sa.String(length=255), nullable=False),
        sa.Column("server_port", sa.Integer(), server_default="389", nullable=False),
        sa.Column("use_ssl", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("use_start_tls", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("base_dn", sa.String(length=255), nullable=False),
        sa.Column("user_search_base", sa.String(length=255), nullable=True),
        sa.Column("computer_search_base", sa.String(length=255), nullable=True),
        sa.Column("group_search_base", sa.String(length=255), nullable=True),
        sa.Column("bind_username", sa.String(length=255), nullable=True),
        sa.Column("encrypted_bind_secret", sa.Text(), nullable=True),
        sa.Column("authentication_method", sa.String(length=30), server_default="simple", nullable=False),
        sa.Column("connection_timeout_seconds", sa.Integer(), server_default="10", nullable=False),
        sa.Column("page_size", sa.Integer(), server_default="500", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("verify_tls", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("ca_certificate_reference", sa.String(length=255), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_status", sa.String(length=30), nullable=True),
        sa.Column("last_test_message", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # 2. active_directory_sync_configurations
    op.create_table(
        "active_directory_sync_configurations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("sync_users_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sync_computers_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sync_groups_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sync_interval_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("auto_create_users", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("auto_disable_missing_users", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("auto_create_devices", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("auto_update_devices", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sync_group_memberships", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("department_mapping_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("organizational_unit_mapping_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("dry_run_default", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("conflict_policy", sa.String(length=30), server_default="review", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["active_directory_connections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id"),
    )

    # 3. active_directory_objects
    op.create_table(
        "active_directory_objects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("object_guid", sa.String(length=64), nullable=False),
        sa.Column("object_sid", sa.String(length=128), nullable=True),
        sa.Column("object_type", sa.String(length=30), nullable=False),
        sa.Column("distinguished_name", sa.String(length=512), nullable=False),
        sa.Column("sam_account_name", sa.String(length=255), nullable=True),
        sa.Column("user_principal_name", sa.String(length=255), nullable=True),
        sa.Column("common_name", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("dns_hostname", sa.String(length=255), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("department", sa.String(length=255), nullable=True),
        sa.Column("job_title", sa.String(length=255), nullable=True),
        sa.Column("operating_system", sa.String(length=255), nullable=True),
        sa.Column("operating_system_version", sa.String(length=255), nullable=True),
        sa.Column("organizational_unit", sa.String(length=512), nullable=True),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("last_logon_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("when_created", sa.DateTime(timezone=True), nullable=True),
        sa.Column("when_changed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_attributes", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sync_status", sa.String(length=30), server_default="discovered", nullable=False),
        sa.Column("review_status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("matched_user_id", sa.String(), nullable=True),
        sa.Column("matched_device_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["active_directory_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "object_guid", name="uq_ad_object_connection_guid"),
    )

    op.create_index("ix_ad_objects_connection_id", "active_directory_objects", ["connection_id"])
    op.create_index("ix_ad_objects_object_guid", "active_directory_objects", ["object_guid"])
    op.create_index("ix_ad_objects_object_sid", "active_directory_objects", ["object_sid"])
    op.create_index("ix_ad_objects_distinguished_name", "active_directory_objects", ["distinguished_name"])
    op.create_index("ix_ad_objects_sam_account_name", "active_directory_objects", ["sam_account_name"])
    op.create_index("ix_ad_objects_user_principal_name", "active_directory_objects", ["user_principal_name"])
    op.create_index("ix_ad_objects_dns_hostname", "active_directory_objects", ["dns_hostname"])
    op.create_index("ix_ad_objects_object_type", "active_directory_objects", ["object_type"])
    op.create_index("ix_ad_objects_sync_status", "active_directory_objects", ["sync_status"])
    op.create_index("ix_ad_objects_review_status", "active_directory_objects", ["review_status"])
    op.create_index("ix_ad_objects_matched_user_id", "active_directory_objects", ["matched_user_id"])
    op.create_index("ix_ad_objects_matched_device_id", "active_directory_objects", ["matched_device_id"])

    # 4. active_directory_sync_runs
    op.create_table(
        "active_directory_sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("connection_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("trigger_type", sa.String(length=30), server_default="manual", nullable=False),
        sa.Column("triggered_by", sa.String(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("users_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("computers_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("groups_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_objects", sa.Integer(), server_default="0", nullable=False),
        sa.Column("updated_objects", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unchanged_objects", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_objects", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conflicts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["active_directory_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_ad_sync_runs_connection_id", "active_directory_sync_runs", ["connection_id"])
    op.create_index("ix_ad_sync_runs_status", "active_directory_sync_runs", ["status"])
    op.create_index("ix_ad_sync_runs_started_at", "active_directory_sync_runs", ["started_at"])

    # 5. active_directory_match_candidates
    op.create_table(
        "active_directory_match_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("directory_object_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_type", sa.String(length=30), nullable=False),
        sa.Column("candidate_user_id", sa.String(), nullable=True),
        sa.Column("candidate_device_id", sa.String(), nullable=True),
        sa.Column("match_score", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("match_level", sa.String(length=30), server_default="none", nullable=False),
        sa.Column("match_status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("matching_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("conflicting_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("recommended_action", sa.String(length=30), server_default="review", nullable=False),
        sa.Column("reviewed_by", sa.String(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["candidate_device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["directory_object_id"], ["active_directory_objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_ad_candidates_directory_object_id", "active_directory_match_candidates", ["directory_object_id"])
    op.create_index("ix_ad_candidates_candidate_user_id", "active_directory_match_candidates", ["candidate_user_id"])
    op.create_index("ix_ad_candidates_candidate_device_id", "active_directory_match_candidates", ["candidate_device_id"])
    op.create_index("ix_ad_candidates_match_status", "active_directory_match_candidates", ["match_status"])


def downgrade() -> None:
    op.drop_table("active_directory_match_candidates")
    op.drop_table("active_directory_sync_runs")
    op.drop_table("active_directory_objects")
    op.drop_table("active_directory_sync_configurations")
    op.drop_table("active_directory_connections")
