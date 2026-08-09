"""Preserve the AD description on approved managed devices.

Revision ID: 8c9d0e1f2a47
Revises: 8b9c0d1e2f36
"""
from alembic import op
import sqlalchemy as sa

revision="8c9d0e1f2a47";down_revision="8b9c0d1e2f36";branch_labels=None;depends_on=None

def upgrade():op.add_column("devices",sa.Column("ad_description",sa.Text()))
def downgrade():op.drop_column("devices","ad_description")
