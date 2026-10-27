"""link local agents to imported managed assets by hostname

Revision ID: v2hagentasset01
Revises: v2gagentfleet01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2hagentasset01"
down_revision = "v2gagentfleet01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "local_agent_registrations",
        sa.Column(
            "managed_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("managed_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_local_agent_registrations_managed_asset_id",
        "local_agent_registrations",
        ["managed_asset_id"],
    )


def downgrade():
    op.drop_index(
        "ix_local_agent_registrations_managed_asset_id",
        table_name="local_agent_registrations",
    )
    op.drop_column("local_agent_registrations", "managed_asset_id")
