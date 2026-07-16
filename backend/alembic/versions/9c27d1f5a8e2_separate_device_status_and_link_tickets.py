"""Separate device lifecycle/monitoring status and link tickets.

Revision ID: 9c27d1f5a8e2
Revises: f4c8e0a4b321
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "9c27d1f5a8e2"
down_revision: Union[str, Sequence[str], None] = "f4c8e0a4b321"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("inventory_status", sa.String(length=30), server_default="Active", nullable=False))
    op.add_column("devices", sa.Column("network_status", sa.String(length=30), server_default="Unknown", nullable=False))
    op.execute("""
        UPDATE devices
        SET inventory_status = CASE
            WHEN lower(status) = 'retired' THEN 'Retired'
            WHEN lower(status) = 'inactive' THEN 'Inactive'
            ELSE 'Active'
        END,
        network_status = CASE
            WHEN lower(status) = 'online' THEN 'Online'
            WHEN lower(status) = 'offline' THEN 'Offline'
            ELSE 'Unknown'
        END
    """)
    op.add_column("tickets", sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_tickets_device_id", "tickets", ["device_id"])
    op.create_foreign_key("fk_tickets_device_id_devices", "tickets", "devices", ["device_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_tickets_device_id_devices", "tickets", type_="foreignkey")
    op.drop_index("ix_tickets_device_id", table_name="tickets")
    op.drop_column("tickets", "device_id")
    op.drop_column("devices", "network_status")
    op.drop_column("devices", "inventory_status")
