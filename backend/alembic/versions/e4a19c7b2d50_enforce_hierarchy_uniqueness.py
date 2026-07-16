"""Enforce case-insensitive hierarchy uniqueness.

Revision ID: e4a19c7b2d50
Revises: d82f4a6c19e3
"""
from alembic import op

revision = "e4a19c7b2d50"
down_revision = "d82f4a6c19e3"
branch_labels = None
depends_on = None

TABLES = ("properties", "buildings", "floors", "rooms", "departments", "network_zones")


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"CREATE UNIQUE INDEX uq_{table}_name_lower ON {table} (lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_network_zones_cidr ON network_zones (cidr) WHERE cidr IS NOT NULL")


def downgrade() -> None:
    op.drop_index("uq_network_zones_cidr", table_name="network_zones")
    for table in reversed(TABLES):
        op.drop_index(f"uq_{table}_name_lower", table_name=table)
