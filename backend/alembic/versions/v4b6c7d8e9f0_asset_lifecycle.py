"""V4B asset lifecycle management.

Revision ID: v4b6c7d8e9f0
Revises: v4a5b6c7d8e9
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4b6c7d8e9f0"
down_revision = "v4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_managed_asset_status", "managed_assets", type_="check")
    op.create_check_constraint("ck_managed_asset_status", "managed_assets", "status IN ('planned','received','deployed','active','in_maintenance','retired')")
    op.add_column("managed_assets", sa.Column("condition", sa.String(20), nullable=True))
    op.add_column("managed_assets", sa.Column("acquisition_date", sa.Date(), nullable=True))
    op.add_column("managed_assets", sa.Column("received_date", sa.Date(), nullable=True))
    op.add_column("managed_assets", sa.Column("deployment_date", sa.Date(), nullable=True))
    op.add_column("managed_assets", sa.Column("retirement_date", sa.Date(), nullable=True))
    op.add_column("managed_assets", sa.Column("retirement_reason", sa.String(40), nullable=True))
    op.add_column("managed_assets", sa.Column("retired_by", sa.String(), nullable=True))
    op.add_column("managed_assets", sa.Column("warranty_start", sa.Date(), nullable=True))
    op.add_column("managed_assets", sa.Column("warranty_end", sa.Date(), nullable=True))
    op.add_column("managed_assets", sa.Column("expected_replacement_date", sa.Date(), nullable=True))
    op.add_column("managed_assets", sa.Column("lifecycle_notes", sa.Text(), nullable=True))
    op.create_foreign_key("fk_managed_assets_retired_by", "managed_assets", "users", ["retired_by"], ["id"], ondelete="SET NULL")
    op.create_check_constraint("ck_managed_asset_condition", "managed_assets", "condition IS NULL OR condition IN ('new','good','fair','poor','damaged')")
    op.create_table(
        "asset_lifecycle_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("managed_assets.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("previous_status", sa.String(24)),
        sa.Column("new_status", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(80)),
        sa.Column("notes", sa.Text()),
        sa.Column("changed_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("changed_by_name", sa.String(180), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_asset_lifecycle_events_asset_created", "asset_lifecycle_events", ["asset_id", "created_at"])
    op.create_index("ix_asset_lifecycle_events_organization_id", "asset_lifecycle_events", ["organization_id"])


def downgrade():
    op.drop_table("asset_lifecycle_events")
    op.drop_constraint("ck_managed_asset_condition", "managed_assets", type_="check")
    op.drop_constraint("fk_managed_assets_retired_by", "managed_assets", type_="foreignkey")
    for column in ("lifecycle_notes","expected_replacement_date","warranty_end","warranty_start","retired_by","retirement_reason","retirement_date","deployment_date","received_date","acquisition_date","condition"):
        op.drop_column("managed_assets", column)
    op.drop_constraint("ck_managed_asset_status", "managed_assets", type_="check")
    op.create_check_constraint("ck_managed_asset_status", "managed_assets", "status IN ('planned','active','in_maintenance','retired')")
