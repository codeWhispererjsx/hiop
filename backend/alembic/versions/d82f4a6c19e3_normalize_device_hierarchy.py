"""Normalize device hierarchy. Revision ID: d82f4a6c19e3; Revises: b31a0d72c4f6."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d82f4a6c19e3"
down_revision = "b31a0d72c4f6"
branch_labels = None
depends_on = None


def common():
    return [sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False), sa.Column("name", sa.String(120), nullable=False), sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False), sa.PrimaryKeyConstraint("id")]


def upgrade() -> None:
    op.create_table("properties", *common(), sa.Column("code", sa.String(40)), sa.Column("address", sa.String(255)), sa.UniqueConstraint("code"))
    op.create_table("buildings", *common(), sa.Column("property_id", postgresql.UUID(as_uuid=True)), sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="RESTRICT")); op.create_index("ix_buildings_property_id", "buildings", ["property_id"])
    op.create_table("floors", *common(), sa.Column("building_id", postgresql.UUID(as_uuid=True)), sa.ForeignKeyConstraint(["building_id"], ["buildings.id"], ondelete="RESTRICT")); op.create_index("ix_floors_building_id", "floors", ["building_id"])
    op.create_table("rooms", *common(), sa.Column("floor_id", postgresql.UUID(as_uuid=True)), sa.ForeignKeyConstraint(["floor_id"], ["floors.id"], ondelete="RESTRICT")); op.create_index("ix_rooms_floor_id", "rooms", ["floor_id"])
    op.create_table("departments", *common(), sa.Column("property_id", postgresql.UUID(as_uuid=True)), sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="RESTRICT")); op.create_index("ix_departments_property_id", "departments", ["property_id"])
    op.create_table("network_zones", *common(), sa.Column("property_id", postgresql.UUID(as_uuid=True)), sa.Column("cidr", sa.String(64)), sa.Column("vlan_id", sa.Integer()), sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="RESTRICT")); op.create_index("ix_network_zones_property_id", "network_zones", ["property_id"])
    for column in ("department_id", "room_id", "network_zone_id"):
        op.add_column("devices", sa.Column(column, postgresql.UUID(as_uuid=True))); op.create_index(f"ix_devices_{column}", "devices", [column])
    op.create_foreign_key("fk_devices_department_id", "devices", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_devices_room_id", "devices", "rooms", ["room_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_devices_network_zone_id", "devices", "network_zones", ["network_zone_id"], ["id"], ondelete="SET NULL")
    op.execute("INSERT INTO departments (id,name,is_active) SELECT gen_random_uuid(), min(trim(department)), true FROM devices WHERE trim(coalesce(department,'')) <> '' GROUP BY lower(trim(department))")
    op.execute("INSERT INTO rooms (id,name,is_active) SELECT gen_random_uuid(), min(trim(location)), true FROM devices WHERE trim(coalesce(location,'')) <> '' GROUP BY lower(trim(location))")
    op.execute("UPDATE devices SET department_id=departments.id FROM departments WHERE lower(trim(devices.department))=lower(departments.name)")
    op.execute("UPDATE devices SET room_id=rooms.id FROM rooms WHERE lower(trim(devices.location))=lower(rooms.name)")


def downgrade() -> None:
    for column in ("network_zone_id", "room_id", "department_id"):
        op.drop_index(f"ix_devices_{column}", table_name="devices"); op.drop_constraint(f"fk_devices_{column}", "devices", type_="foreignkey"); op.drop_column("devices", column)
    for table in ("network_zones", "departments", "rooms", "floors", "buildings", "properties"): op.drop_table(table)
