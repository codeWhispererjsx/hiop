"""add minimal V4A managed asset intelligence

Revision ID: v4a1b2c3d4e5
Revises: v3freeze0a1b2c3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="v4a1b2c3d4e5";down_revision="v3freeze0a1b2c3";branch_labels=None;depends_on=None


def upgrade():
    op.execute("CREATE SEQUENCE managed_asset_number_seq START 1")
    op.create_table("managed_assets",
        sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("asset_number",sa.String(24),nullable=False,unique=True),
        sa.Column("device_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("devices.id",ondelete="RESTRICT"),unique=True),sa.Column("name",sa.String(180),nullable=False),
        sa.Column("asset_tag",sa.String(80),unique=True),sa.Column("device_type",sa.String(80),nullable=False),sa.Column("status",sa.String(24),nullable=False,server_default="active"),
        sa.Column("ci_category",sa.String(24),nullable=False,server_default="device"),sa.Column("vendor",sa.String(120)),sa.Column("model",sa.String(160)),sa.Column("serial_number",sa.String(180)),
        sa.Column("department_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("departments.id",ondelete="SET NULL")),sa.Column("department_name",sa.String(120)),
        sa.Column("room_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("rooms.id",ondelete="SET NULL")),sa.Column("location_name",sa.String(160)),sa.Column("business_owner",sa.String(180)),sa.Column("technical_owner",sa.String(180)),sa.Column("description",sa.Text()),
        sa.Column("source",sa.String(30),nullable=False,server_default="manual"),sa.Column("field_sources",postgresql.JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_by",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),sa.Column("updated_by",sa.String(),sa.ForeignKey("users.id",ondelete="SET NULL")),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('planned','active','in_maintenance','retired')",name="ck_managed_asset_status"),sa.CheckConstraint("ci_category IN ('device','network','server','application','service','other')",name="ck_managed_asset_category"))
    op.create_index("ix_managed_assets_status_type","managed_assets",["status","device_type"]);op.create_index("ix_managed_assets_serial_number","managed_assets",["serial_number"]);op.create_index("ix_managed_assets_department_id","managed_assets",["department_id"]);op.create_index("ix_managed_assets_room_id","managed_assets",["room_id"])
    op.execute("""INSERT INTO managed_assets (id,asset_number,device_id,name,asset_tag,device_type,status,ci_category,department_id,department_name,room_id,location_name,description,source,field_sources,created_at,updated_at)
        SELECT gen_random_uuid(),'HIOP-'||lpad(row_number() over(order by created_at,id)::text,6,'0'),id,hostname,asset_tag,device_type,
        CASE WHEN inventory_status='Retired' THEN 'retired' ELSE 'active' END,
        CASE WHEN lower(device_type) IN ('switch','router','firewall','access point','network appliance') THEN 'network' WHEN lower(device_type)='server' THEN 'server' ELSE 'device' END,
        department_id,nullif(department,''),room_id,nullif(location,''),description,CASE WHEN mac_address IS NULL THEN 'manual' ELSE 'discovery' END,'{"technical_identity":"Device","organizational_metadata":"Imported from existing inventory"}'::jsonb,created_at,updated_at FROM devices""")
    op.execute("SELECT setval('managed_asset_number_seq',GREATEST((SELECT count(*) FROM managed_assets),1))")


def downgrade():
    op.drop_table("managed_assets");op.execute("DROP SEQUENCE managed_asset_number_seq")
