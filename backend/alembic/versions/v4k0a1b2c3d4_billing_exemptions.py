"""Add platform billing exemptions.

Revision ID: v4k0a1b2c3d4
Revises: v4j0a1b2c3d4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="v4k0a1b2c3d4"
down_revision="v4j0a1b2c3d4"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("organization_subscriptions", sa.Column("billing_exempt", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("organization_subscriptions", sa.Column("billing_exemption_reason", sa.Text(), nullable=True))
    op.add_column("organization_subscriptions", sa.Column("billing_exempted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organization_subscriptions", sa.Column("billing_exempted_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_subscription_billing_exempted_by", "organization_subscriptions", "users", ["billing_exempted_by"], ["id"], ondelete="SET NULL")

def downgrade():
    op.drop_constraint("fk_subscription_billing_exempted_by", "organization_subscriptions", type_="foreignkey")
    op.drop_column("organization_subscriptions", "billing_exempted_by")
    op.drop_column("organization_subscriptions", "billing_exempted_at")
    op.drop_column("organization_subscriptions", "billing_exemption_reason")
    op.drop_column("organization_subscriptions", "billing_exempt")
