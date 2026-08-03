"""Create the configured primary property when hierarchy is empty.

Revision ID: 5f6a7b8c9d03
Revises: 4e5f6a7b8c92
"""
from alembic import op
import sqlalchemy as sa

revision = "5f6a7b8c9d03"
down_revision = "4e5f6a7b8c92"
branch_labels = None
depends_on = None

PROPERTY_ID = "b9cbd0f2-d2be-4b25-a6c9-1a4e7b576e18"


def upgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT count(*) FROM properties")).scalar_one() == 0:
        name = connection.execute(sa.text(
            "SELECT value FROM system_settings WHERE key = 'organization.property_name'"
        )).scalar_one_or_none() or "Primary Property"
        connection.execute(sa.text(
            "INSERT INTO properties (id, name, is_active, type, timezone, operational_status) "
            "VALUES (:id, :name, true, 'hotel', 'Africa/Lagos', 'active')"
        ), {"id": PROPERTY_ID, "name": name})
        connection.execute(sa.text(
            "UPDATE devices SET property_id = :id WHERE property_id IS NULL"
        ), {"id": PROPERTY_ID})


def downgrade():
    connection = op.get_bind()
    connection.execute(sa.text("UPDATE devices SET property_id = NULL WHERE property_id = :id"), {"id": PROPERTY_ID})
    connection.execute(sa.text("DELETE FROM properties WHERE id = :id"), {"id": PROPERTY_ID})
