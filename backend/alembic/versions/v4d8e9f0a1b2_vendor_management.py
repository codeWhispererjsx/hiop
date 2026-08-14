"""V4D operational vendor management.

Revision ID: v4d8e9f0a1b2
Revises: v4c7d8e9f0a1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="v4d8e9f0a1b2"
down_revision="v4c7d8e9f0a1"
branch_labels=None
depends_on=None

def upgrade():
    op.execute("CREATE SEQUENCE IF NOT EXISTS operational_vendor_number_seq START WITH 1")
    op.add_column("vendors",sa.Column("organization_id",postgresql.UUID(as_uuid=True),nullable=True))
    op.add_column("vendors",sa.Column("vendor_code",sa.String(40),nullable=True))
    op.add_column("vendors",sa.Column("vendor_type",sa.String(30),server_default="other",nullable=False))
    op.add_column("vendors",sa.Column("description",sa.Text(),nullable=True))
    op.add_column("vendors",sa.Column("website",sa.String(500),nullable=True))
    op.add_column("vendors",sa.Column("primary_email",sa.String(255),nullable=True))
    op.add_column("vendors",sa.Column("primary_phone",sa.String(80),nullable=True))
    op.add_column("vendors",sa.Column("address",sa.Text(),nullable=True))
    op.add_column("vendors",sa.Column("country",sa.String(100),nullable=True))
    op.add_column("vendors",sa.Column("notes",sa.Text(),nullable=True))
    op.add_column("vendors",sa.Column("support_agreement_reference",sa.String(120),nullable=True))
    op.add_column("vendors",sa.Column("renewal_date",sa.Date(),nullable=True))
    op.add_column("vendors",sa.Column("products_services",sa.Text(),server_default="[]",nullable=False))
    op.create_foreign_key("fk_vendors_organization","vendors","organizations",["organization_id"],["id"],ondelete="RESTRICT")
    op.execute("UPDATE vendors SET organization_id=(SELECT id FROM organizations ORDER BY created_at LIMIT 1) WHERE organization_id IS NULL")
    op.alter_column("vendors","organization_id",nullable=False)
    op.create_index("ix_vendors_organization_id","vendors",["organization_id"])
    op.create_index("ix_vendors_vendor_type","vendors",["vendor_type"])
    op.create_index("uq_vendors_org_code","vendors",["organization_id","vendor_code"],unique=True,postgresql_where=sa.text("vendor_code IS NOT NULL"))
    op.create_index("uq_vendors_org_name","vendors",["organization_id",sa.text("lower(legal_name)")],unique=True)
    op.add_column("vendor_contacts",sa.Column("department",sa.String(120),nullable=True))
    op.add_column("vendor_contacts",sa.Column("notes",sa.Text(),nullable=True))
    op.add_column("vendor_contacts",sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.add_column("managed_assets",sa.Column("vendor_id",postgresql.UUID(as_uuid=True),nullable=True))
    op.create_foreign_key("fk_managed_assets_vendor","managed_assets","vendors",["vendor_id"],["id"],ondelete="SET NULL")
    op.create_index("ix_managed_assets_vendor_id","managed_assets",["vendor_id"])
    op.add_column("asset_procurements",sa.Column("vendor_id",postgresql.UUID(as_uuid=True),nullable=True))
    op.create_foreign_key("fk_asset_procurements_vendor","asset_procurements","vendors",["vendor_id"],["id"],ondelete="SET NULL")
    op.create_index("ix_asset_procurements_vendor_id","asset_procurements",["vendor_id"])

def downgrade():
    op.drop_index("ix_asset_procurements_vendor_id",table_name="asset_procurements")
    op.drop_constraint("fk_asset_procurements_vendor","asset_procurements",type_="foreignkey")
    op.drop_column("asset_procurements","vendor_id")
    op.drop_index("ix_managed_assets_vendor_id",table_name="managed_assets")
    op.drop_constraint("fk_managed_assets_vendor","managed_assets",type_="foreignkey")
    op.drop_column("managed_assets","vendor_id")
    op.drop_column("vendor_contacts","updated_at");op.drop_column("vendor_contacts","notes");op.drop_column("vendor_contacts","department")
    op.drop_index("uq_vendors_org_name",table_name="vendors");op.drop_index("uq_vendors_org_code",table_name="vendors");op.drop_index("ix_vendors_vendor_type",table_name="vendors");op.drop_index("ix_vendors_organization_id",table_name="vendors")
    op.drop_constraint("fk_vendors_organization","vendors",type_="foreignkey")
    for name in ("products_services","renewal_date","support_agreement_reference","notes","country","address","primary_phone","primary_email","website","description","vendor_type","vendor_code","organization_id"):op.drop_column("vendors",name)
    op.execute("DROP SEQUENCE IF EXISTS operational_vendor_number_seq")
