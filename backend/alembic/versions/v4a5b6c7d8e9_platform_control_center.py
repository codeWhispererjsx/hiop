"""V4A.5 platform control center and organization ownership.

Revision ID: v4a5b6c7d8e9
Revises: v4a1b2c3d4e5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="v4a5b6c7d8e9";down_revision="v4a1b2c3d4e5";branch_labels=None;depends_on=None

def upgrade():
    op.add_column("organizations",sa.Column("contact_email",sa.String(255)))
    op.add_column("organizations",sa.Column("contact_phone",sa.String(40)))
    op.add_column("organizations",sa.Column("notes",sa.Text()))
    op.add_column("organizations",sa.Column("created_by",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")))
    op.add_column("organizations",sa.Column("administrator_id",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")))
    op.add_column("organizations",sa.Column("hiop_version",sa.String(30),nullable=False,server_default="4A.5"))
    op.add_column("organizations",sa.Column("last_activity_at",sa.DateTime(timezone=True)))
    op.add_column("users",sa.Column("organization_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("organizations.id",ondelete="RESTRICT")))
    op.create_index("ix_users_organization_id","users",["organization_id"])
    op.add_column("managed_assets",sa.Column("organization_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("organizations.id",ondelete="RESTRICT")))
    op.create_index("ix_managed_assets_organization_id","managed_assets",["organization_id"])
    op.execute("""
    DO $$ DECLARE oid uuid; pname text; pcode text;
    BEGIN
      SELECT id INTO oid FROM organizations ORDER BY created_at LIMIT 1;
      IF oid IS NULL THEN
        SELECT COALESCE(name,'Initial Organization'),COALESCE(NULLIF(lower(regexp_replace(name,'[^a-zA-Z0-9]+','-','g')),''),'initial-organization') INTO pname,pcode FROM properties ORDER BY name LIMIT 1;
        pname:=COALESCE(pname,'Initial Organization');pcode:=COALESCE(pcode,'initial-organization');
        INSERT INTO organizations(id,name,code,type,timezone,status,hiop_version,created_at,updated_at) VALUES(gen_random_uuid(),pname,pcode,'hospitality_group','Africa/Lagos','active','4A.5',now(),now()) RETURNING id INTO oid;
      END IF;
      UPDATE users SET role='admin' WHERE role='superadmin';
      UPDATE properties SET organization_id=oid WHERE organization_id IS NULL;
      UPDATE devices SET property_id=(SELECT id FROM properties WHERE organization_id=oid ORDER BY name LIMIT 1) WHERE property_id IS NULL;
      UPDATE users SET organization_id=oid WHERE role<>'platformadmin' AND organization_id IS NULL;
      UPDATE managed_assets SET organization_id=oid WHERE organization_id IS NULL;
      UPDATE operational_incidents SET organization_id=oid WHERE organization_id IS NULL;
      UPDATE organizations SET administrator_id=(SELECT id FROM users WHERE role='admin' AND organization_id=oid ORDER BY created_at LIMIT 1) WHERE id=oid AND administrator_id IS NULL;
    END $$;
    """)
    op.alter_column("managed_assets","organization_id",nullable=False)

def downgrade():
    op.drop_index("ix_managed_assets_organization_id",table_name="managed_assets");op.drop_column("managed_assets","organization_id")
    op.drop_index("ix_users_organization_id",table_name="users");op.drop_column("users","organization_id")
    for column in ("last_activity_at","hiop_version","administrator_id","created_by","notes","contact_phone","contact_email"):op.drop_column("organizations",column)
