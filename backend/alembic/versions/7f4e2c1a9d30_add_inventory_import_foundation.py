"""Add intelligent inventory import foundation.

Revision ID: 7f4e2c1a9d30
Revises: c87d380fc50a
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "7f4e2c1a9d30"
down_revision = "c87d380fc50a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("import_type", sa.String(64), nullable=False),
        sa.Column("file_format", sa.String(16), nullable=False),
        sa.Column("uploaded_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processing_started_at", sa.DateTime(timezone=True)),
        sa.Column("processing_completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(10), server_default="uploaded", nullable=False),
        sa.Column("total_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("successful_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("matched_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_rows", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_summary", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('uploaded', 'validating', 'processing', 'completed', 'partial', 'failed')", name="import_session_status"),
        sa.CheckConstraint("total_rows >= 0", name="ck_import_sessions_total_rows_nonnegative"),
        sa.CheckConstraint("processed_rows >= 0", name="ck_import_sessions_processed_rows_nonnegative"),
        sa.CheckConstraint("successful_rows >= 0", name="ck_import_sessions_successful_rows_nonnegative"),
        sa.CheckConstraint("failed_rows >= 0", name="ck_import_sessions_failed_rows_nonnegative"),
        sa.CheckConstraint("duplicate_rows >= 0", name="ck_import_sessions_duplicate_rows_nonnegative"),
        sa.CheckConstraint("matched_rows >= 0", name="ck_import_sessions_matched_rows_nonnegative"),
        sa.CheckConstraint("skipped_rows >= 0", name="ck_import_sessions_skipped_rows_nonnegative"),
        sa.CheckConstraint("processed_rows <= total_rows", name="ck_import_sessions_processed_within_total"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_import_sessions_status", "import_sessions", ["status"])
    op.create_index("ix_import_sessions_uploaded_by", "import_sessions", ["uploaded_by"])
    op.create_index("ix_import_sessions_uploaded_at", "import_sessions", ["uploaded_at"])

    op.create_table(
        "imported_devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("import_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_tag", sa.String(100)),
        sa.Column("hostname", sa.String(255)),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("mac_address", sa.String(17)),
        sa.Column("department_name", sa.String(120)),
        sa.Column("building_name", sa.String(120)),
        sa.Column("floor_name", sa.String(120)),
        sa.Column("room_name", sa.String(120)),
        sa.Column("network_zone", sa.String(120)),
        sa.Column("vendor", sa.String(128)),
        sa.Column("brand", sa.String(128)),
        sa.Column("model", sa.String(128)),
        sa.Column("serial_number", sa.String(128)),
        sa.Column("inventory_status", sa.String(32)),
        sa.Column("raw_data", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("validation_status", sa.String(9), server_default="pending", nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("validation_status IN ('pending', 'valid', 'warning', 'duplicate', 'invalid')", name="import_validation_status"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imported_devices_import_session_id", "imported_devices", ["import_session_id"])
    op.create_index("ix_imported_devices_asset_tag", "imported_devices", ["asset_tag"])
    op.create_index("ix_imported_devices_hostname", "imported_devices", ["hostname"])
    op.create_index("ix_imported_devices_ip_address", "imported_devices", ["ip_address"])
    op.create_index("ix_imported_devices_mac_address", "imported_devices", ["mac_address"])
    op.create_index("ix_imported_devices_validation_status", "imported_devices", ["validation_status"])
    op.create_index("uq_imported_devices_session_asset_tag", "imported_devices", ["import_session_id", sa.text("lower(asset_tag)")], unique=True, postgresql_where=sa.text("asset_tag IS NOT NULL"))
    op.create_index("uq_imported_devices_session_mac", "imported_devices", ["import_session_id", sa.text("lower(mac_address)")], unique=True, postgresql_where=sa.text("mac_address IS NOT NULL"))


def downgrade() -> None:
    op.drop_table("imported_devices")
    op.drop_table("import_sessions")
