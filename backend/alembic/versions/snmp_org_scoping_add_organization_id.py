"""Add organization_id to SNMP tables for multi-tenant support.

Revision ID: snmp_org_scoping
Revises: c9e4a7b2d610
Create Date: 2026-08-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "snmp_org_scoping"
down_revision = "90a504ea5308"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    # Add organization_id to snmp_credentials
    op.add_column(
        "snmp_credentials",
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    )
    
    # Add organization_id to snmp_targets
    op.add_column(
        "snmp_targets", 
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True)
    )
    
    # Migrate existing data - assign to first organization as default
    op.execute("""
        UPDATE snmp_credentials 
        SET organization_id = (SELECT id FROM organizations LIMIT 1)
        WHERE organization_id IS NULL
    """)
    
    op.execute("""
        UPDATE snmp_targets 
        SET organization_id = (SELECT id FROM organizations LIMIT 1)
        WHERE organization_id IS NULL
    """)
    
    # Drop the old global unique constraint on name
    op.drop_constraint("snmp_credentials_name_key", "snmp_credentials", type_="unique")
    
    # Add composite unique constraint scoped to organization
    op.create_unique_constraint(
        "uq_snmp_credentials_org_name", 
        "snmp_credentials", 
        ["organization_id", "name"]
    )
    
    # Add indexes for organization filtering
    op.create_index("ix_snmp_credentials_organization_id", "snmp_credentials", ["organization_id"])
    op.create_index("ix_snmp_targets_organization_id", "snmp_targets", ["organization_id"])
    
    # Make organization_id NOT NULL after migration
    op.alter_column("snmp_credentials", "organization_id", nullable=False)
    op.alter_column("snmp_targets", "organization_id", nullable=False)


def downgrade() -> None:
    # Remove the NOT NULL constraint first
    op.alter_column("snmp_credentials", "organization_id", nullable=True)
    op.alter_column("snmp_targets", "organization_id", nullable=True)
    
    # Remove composite unique constraint
    op.drop_constraint("uq_snmp_credentials_org_name", "snmp_credentials", type_="unique")
    
    # Restore old global unique constraint
    op.create_unique_constraint("snmp_credentials_name_key", "snmp_credentials", ["name"])
    
    # Remove indexes
    op.drop_index("ix_snmp_targets_organization_id", "snmp_targets")
    op.drop_index("ix_snmp_credentials_organization_id", "snmp_credentials")
    
    # Remove columns
    op.drop_column("snmp_targets", "organization_id")
    op.drop_column("snmp_credentials", "organization_id")