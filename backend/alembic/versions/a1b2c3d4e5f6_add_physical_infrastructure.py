"""add physical infrastructure hierarchy for v3"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a1b2c3d4e5f6"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("buildings", sa.Column("code", sa.String(40), nullable=True))
    op.add_column("buildings", sa.Column("description", sa.String(255), nullable=True))
    op.add_column("buildings", sa.Column("number_of_floors", sa.Integer(), nullable=True))
    op.add_column("buildings", sa.Column("status", sa.String(20), server_default="active", nullable=False))
    op.add_column("floors", sa.Column("floor_number", sa.Integer(), nullable=True))
    op.add_column("floors", sa.Column("display_name", sa.String(120), nullable=True))
    op.add_column("floors", sa.Column("description", sa.String(255), nullable=True))
    op.add_column("floors", sa.Column("zone_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("floors", sa.Column("status", sa.String(20), server_default="active", nullable=False))
    op.create_table("zones",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("floor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("floors.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("name", sa.String(120), nullable=False), sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("code", sa.String(40)), sa.Column("type", sa.String(40), server_default="unknown", nullable=False),
        sa.Column("description", sa.String(255)), sa.Column("status", sa.String(20), server_default="active", nullable=False))
    op.create_index("ix_zones_floor_id", "zones", ["floor_id"])
    op.create_index("ix_zones_code", "zones", ["code"])
    op.add_column("rooms", sa.Column("zone_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)); op.create_index("ix_rooms_zone_id", "rooms", ["zone_id"])
    op.add_column("departments", sa.Column("zone_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("zones.id", ondelete="SET NULL"), nullable=True)); op.create_index("ix_departments_zone_id", "departments", ["zone_id"])
    for name in ("building_id", "floor_id", "zone_id"):
        ref = {"building_id":"buildings", "floor_id":"floors", "zone_id":"zones"}[name]
        op.add_column("devices", sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{ref}.id", ondelete="SET NULL"), nullable=True)); op.create_index(f"ix_devices_{name}", "devices", [name])

def downgrade():
    for name in ("building_id", "floor_id", "zone_id"):
        op.drop_index(f"ix_devices_{name}", table_name="devices"); op.drop_column("devices", name)
    op.drop_index("ix_departments_zone_id", table_name="departments"); op.drop_column("departments", "zone_id")
    op.drop_index("ix_rooms_zone_id", table_name="rooms"); op.drop_column("rooms", "zone_id")
    op.drop_index("ix_zones_code", table_name="zones"); op.drop_index("ix_zones_floor_id", table_name="zones"); op.drop_table("zones")
    for name in ("status", "zone_count", "description", "display_name", "floor_number"): op.drop_column("floors", name)
    for name in ("status", "number_of_floors", "description", "code"): op.drop_column("buildings", name)
