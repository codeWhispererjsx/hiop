"""Add indexes for high-frequency operational queries.

Revision ID: a71c8d9e4f20
Revises: e4a19c7b2d50
"""
from alembic import op

revision = "a71c8d9e4f20"
down_revision = "e4a19c7b2d50"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_devices_hostname", "devices", ["hostname"])
    op.create_index("ix_devices_ip_address", "devices", ["ip_address"])
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_alerts_acknowledged_created_at", "alerts", ["acknowledged", "created_at"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("ix_network_scans_scanned_at", "network_scans", ["scanned_at"])
    op.create_index("ix_network_scans_device_scanned_at", "network_scans", ["device_id", "scanned_at"])


def downgrade() -> None:
    op.drop_index("ix_network_scans_device_scanned_at", table_name="network_scans")
    op.drop_index("ix_network_scans_scanned_at", table_name="network_scans")
    op.drop_index("ix_audit_logs_created_at", table_name="audit_logs")
    op.drop_index("ix_alerts_acknowledged_created_at", table_name="alerts")
    op.drop_index("ix_tickets_status", table_name="tickets")
    op.drop_index("ix_devices_ip_address", table_name="devices")
    op.drop_index("ix_devices_hostname", table_name="devices")
