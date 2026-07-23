"""Add AD synchronization progress, history, checkpoints, and errors.

Revision ID: a7c3e5f90124
Revises: f4b8c2d9a731
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a7c3e5f90124"
down_revision = "f4b8c2d9a731"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_empty_object = sa.text("'{}'::jsonb")
    json_empty_list = sa.text("'[]'::jsonb")
    op.add_column("active_directory_sync_configurations", sa.Column(
        "checkpoints", postgresql.JSONB(astext_type=sa.Text()),
        server_default=json_empty_object, nullable=False,
    ))
    for name, default in (
        ("object_types", json_empty_list),
        ("checkpoint_before", json_empty_object),
        ("checkpoint_after", json_empty_object),
        ("per_type_status", json_empty_object),
        ("progress", json_empty_object),
        ("dry_run_results", json_empty_object),
    ):
        op.add_column("active_directory_sync_runs", sa.Column(
            name, postgresql.JSONB(astext_type=sa.Text()), server_default=default, nullable=False
        ))
    op.add_column("active_directory_sync_runs", sa.Column(
        "sync_mode", sa.String(length=20), server_default="full", nullable=False
    ))
    op.add_column("active_directory_sync_runs", sa.Column(
        "cancel_requested_at", sa.DateTime(timezone=True), nullable=True
    ))
    op.add_column("active_directory_sync_runs", sa.Column(
        "restored_objects", sa.Integer(), server_default="0", nullable=False
    ))
    op.drop_constraint("ck_ad_sync_run_nonnegative_counts", "active_directory_sync_runs", type_="check")
    op.create_check_constraint(
        "ck_ad_sync_run_nonnegative_counts", "active_directory_sync_runs",
        "users_seen >= 0 AND computers_seen >= 0 AND groups_seen >= 0 "
        "AND created_objects >= 0 AND updated_objects >= 0 AND unchanged_objects >= 0 "
        "AND missing_objects >= 0 AND restored_objects >= 0 "
        "AND conflicts >= 0 AND errors_count >= 0",
    )
    op.create_check_constraint(
        "ck_ad_sync_run_mode", "active_directory_sync_runs", "sync_mode IN ('full','incremental')"
    )
    op.add_column("active_directory_objects", sa.Column("missing_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("active_directory_objects", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column("active_directory_objects", sa.Column("last_sync_run_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_ad_objects_last_sync_run", "active_directory_objects",
        "active_directory_sync_runs", ["last_sync_run_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_ad_objects_missing_since", "active_directory_objects", ["missing_since"])
    op.create_index("ix_ad_objects_last_sync_run_id", "active_directory_objects", ["last_sync_run_id"])

    op.create_table(
        "active_directory_object_changes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("directory_object_id", sa.String(length=36), nullable=False),
        sa.Column("sync_run_id", sa.String(length=36), nullable=False),
        sa.Column("change_type", sa.String(length=30), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(astext_type=sa.Text()), server_default=json_empty_list, nullable=False),
        sa.Column("before_values", postgresql.JSONB(astext_type=sa.Text()), server_default=json_empty_object, nullable=False),
        sa.Column("after_values", postgresql.JSONB(astext_type=sa.Text()), server_default=json_empty_object, nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "change_type IN ('created','updated','moved','renamed','enabled','disabled','missing','restored')",
            name="ck_ad_object_change_type",
        ),
        sa.ForeignKeyConstraint(["directory_object_id"], ["active_directory_objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["active_directory_sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ad_object_changes_object_id", "active_directory_object_changes", ["directory_object_id"])
    op.create_index("ix_ad_object_changes_run_id", "active_directory_object_changes", ["sync_run_id"])
    op.create_index("ix_ad_object_changes_detected_at", "active_directory_object_changes", ["detected_at"])

    op.create_table(
        "active_directory_sync_errors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_run_id", sa.String(length=36), nullable=False),
        sa.Column("object_type", sa.String(length=30), nullable=True),
        sa.Column("safe_object_reference", sa.String(length=128), nullable=True),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=False),
        sa.Column("safe_message", sa.String(length=500), nullable=False),
        sa.Column("retryable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sync_run_id"], ["active_directory_sync_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ad_sync_errors_run_id", "active_directory_sync_errors", ["sync_run_id"])
    op.create_index("ix_ad_sync_errors_created_at", "active_directory_sync_errors", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ad_sync_errors_created_at", table_name="active_directory_sync_errors")
    op.drop_index("ix_ad_sync_errors_run_id", table_name="active_directory_sync_errors")
    op.drop_table("active_directory_sync_errors")
    op.drop_index("ix_ad_object_changes_detected_at", table_name="active_directory_object_changes")
    op.drop_index("ix_ad_object_changes_run_id", table_name="active_directory_object_changes")
    op.drop_index("ix_ad_object_changes_object_id", table_name="active_directory_object_changes")
    op.drop_table("active_directory_object_changes")
    op.drop_index("ix_ad_objects_last_sync_run_id", table_name="active_directory_objects")
    op.drop_index("ix_ad_objects_missing_since", table_name="active_directory_objects")
    op.drop_constraint("fk_ad_objects_last_sync_run", "active_directory_objects", type_="foreignkey")
    op.drop_column("active_directory_objects", "last_sync_run_id")
    op.drop_column("active_directory_objects", "content_hash")
    op.drop_column("active_directory_objects", "missing_since")
    op.drop_constraint("ck_ad_sync_run_mode", "active_directory_sync_runs", type_="check")
    op.drop_constraint("ck_ad_sync_run_nonnegative_counts", "active_directory_sync_runs", type_="check")
    op.create_check_constraint(
        "ck_ad_sync_run_nonnegative_counts", "active_directory_sync_runs",
        "users_seen >= 0 AND computers_seen >= 0 AND groups_seen >= 0 "
        "AND created_objects >= 0 AND updated_objects >= 0 AND unchanged_objects >= 0 "
        "AND missing_objects >= 0 AND conflicts >= 0 AND errors_count >= 0",
    )
    for name in (
        "restored_objects", "cancel_requested_at", "sync_mode", "dry_run_results",
        "progress", "per_type_status", "checkpoint_after", "checkpoint_before", "object_types",
    ):
        op.drop_column("active_directory_sync_runs", name)
    op.drop_column("active_directory_sync_configurations", "checkpoints")
