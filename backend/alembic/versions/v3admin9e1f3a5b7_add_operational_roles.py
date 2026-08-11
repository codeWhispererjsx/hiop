"""add V3 operational administration roles

Revision ID: v3admin9e1f3a5b7
Revises: v3c8d0e2f4a6
"""
from alembic import op
import sqlalchemy as sa

revision = "v3admin9e1f3a5b7"
down_revision = "v3c8d0e2f4a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    # Legacy admin was the highest application role. Preserve that access explicitly.
    op.execute("UPDATE users SET role = 'superadmin' WHERE role = 'admin'")
    op.execute("UPDATE users SET role = 'viewer' WHERE role = 'staff'")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'superadmin'")
    op.execute("UPDATE users SET role = 'staff' WHERE role = 'viewer'")
    op.drop_column("users", "last_login_at")
