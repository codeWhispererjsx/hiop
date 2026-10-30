"""Allow organization-defined managed asset numbers.

Revision ID: naming0a1b2c3
Revises: v2i_alert_rule_defaults
"""
from alembic import op
import sqlalchemy as sa

revision = "naming0a1b2c3"
down_revision = "v2i_alert_rule_defaults"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "managed_assets",
        "asset_number",
        existing_type=sa.String(length=24),
        type_=sa.String(length=120),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "managed_assets",
        "asset_number",
        existing_type=sa.String(length=120),
        type_=sa.String(length=24),
        existing_nullable=False,
    )
