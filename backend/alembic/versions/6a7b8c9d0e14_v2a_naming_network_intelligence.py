"""V2A naming and network intelligence fields.

Revision ID: 6a7b8c9d0e14
Revises: 3d4e5f6a7b81
"""
from alembic import op
import sqlalchemy as sa

revision = "6a7b8c9d0e14"
down_revision = "3d4e5f6a7b81"
branch_labels = None
depends_on = None

def upgrade():
    for name, column in (
        ("fqdn", sa.Column("fqdn", sa.String(255))),
        ("dns_status", sa.Column("dns_status", sa.String(40), nullable=False, server_default="not_attempted")),
        ("friendly_name", sa.Column("friendly_name", sa.String(255))),
        ("department", sa.Column("department", sa.String(120))),
        ("device_number", sa.Column("device_number", sa.String(40))),
        ("description", sa.Column("description", sa.Text())),
        ("description_source", sa.Column("description_source", sa.String(40))),
        ("location", sa.Column("location", sa.String(160))),
    ): op.add_column("enterprise_discovery_results", column)
    op.add_column("enterprise_discovery_dhcp_leases", sa.Column("is_reservation", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("enterprise_discovery_dhcp_leases", sa.Column("reservation_name", sa.String(255)))
    op.add_column("enterprise_discovery_dhcp_leases", sa.Column("description", sa.Text()))
    op.add_column("devices", sa.Column("description", sa.Text()))
    op.add_column("devices", sa.Column("description_source", sa.String(40)))

def downgrade():
    for name in ("description_source", "description"): op.drop_column("devices", name)
    for name in ("description", "reservation_name", "is_reservation"): op.drop_column("enterprise_discovery_dhcp_leases", name)
    for name in ("location", "description_source", "description", "device_number", "department", "friendly_name", "dns_status", "fqdn"): op.drop_column("enterprise_discovery_results", name)
