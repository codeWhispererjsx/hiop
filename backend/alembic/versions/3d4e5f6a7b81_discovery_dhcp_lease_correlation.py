"""Discovery Intelligence DHCP lease correlation.

Revision ID: 3d4e5f6a7b81
Revises: 2c3d4e5f6a70
"""
from alembic import op
from app.models.discovery_intelligence import DiscoveryDHCPLease

revision="3d4e5f6a7b81";down_revision="2c3d4e5f6a70";branch_labels=None;depends_on=None

def upgrade(): DiscoveryDHCPLease.__table__.create(op.get_bind(),checkfirst=True)
def downgrade(): DiscoveryDHCPLease.__table__.drop(op.get_bind(),checkfirst=True)
