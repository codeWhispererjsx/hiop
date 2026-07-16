"""Backfill unambiguous ticket device links.

Revision ID: b31a0d72c4f6
Revises: 9c27d1f5a8e2
"""
from typing import Sequence, Union

from alembic import op

revision: str = "b31a0d72c4f6"
down_revision: Union[str, Sequence[str], None] = "9c27d1f5a8e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE tickets AS ticket
        SET device_id = device.id
        FROM devices AS device
        WHERE ticket.device_id IS NULL
          AND (
            lower(ticket.title) LIKE '%' || lower(device.hostname) || '%'
            OR lower(ticket.description) LIKE '%' || lower(device.hostname) || '%'
            OR lower(ticket.title) LIKE '%' || lower(device.asset_tag) || '%'
            OR lower(ticket.description) LIKE '%' || lower(device.asset_tag) || '%'
            OR lower(ticket.title) LIKE '%' || lower(device.ip_address) || '%'
            OR lower(ticket.description) LIKE '%' || lower(device.ip_address) || '%'
            OR lower(ticket.title) LIKE '%' || lower(device.serial_number) || '%'
            OR lower(ticket.description) LIKE '%' || lower(device.serial_number) || '%'
          )
    """)


def downgrade() -> None:
    # Links may have been added legitimately after this migration; do not erase them.
    pass
