"""Fix SNMP credential unique constraint to be organization-scoped.

Revision ID: snmp_fix_unique
Revises: snmp_org_scoping
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "snmp_fix_unique"
down_revision = "snmp_org_scoping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the old global unique constraint on name
    op.drop_constraint("snmp_credentials_name_key", "snmp_credentials", type_="unique")
    
    # Add composite unique constraint scoped to organization
    op.create_unique_constraint(
        "uq_snmp_credentials_org_name", 
        "snmp_credentials", 
        ["organization_id", "name"]
    )


def downgrade() -> None:
    # Remove composite unique constraint
    op.drop_constraint("uq_snmp_credentials_org_name", "snmp_credentials", type_="unique")
    
    # Restore old global unique constraint
    op.create_unique_constraint("snmp_credentials_name_key", "snmp_credentials", ["name"])