"""Allow an unknown MAC address on managed devices.

Revision ID: 4e5f6a7b8c92
Revises: 3d4e5f6a7b81
"""
from alembic import op
import sqlalchemy as sa

revision = "4e5f6a7b8c92"
down_revision = "3d4e5f6a7b81"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("devices", "mac_address", existing_type=sa.String(), nullable=True)


def downgrade():
    op.execute("UPDATE devices SET mac_address = 'UNKNOWN-' || id::text WHERE mac_address IS NULL")
    op.alter_column("devices", "mac_address", existing_type=sa.String(), nullable=False)
