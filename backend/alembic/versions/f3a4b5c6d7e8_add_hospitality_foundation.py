"""add organization and property context for v3 hospitality foundation

Revision ID: f3a4b5c6d7e8
Revises: e7f8a9b0c1d2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f3a4b5c6d7e8"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("type", sa.String(40), server_default="hospitality_group", nullable=False),
        sa.Column("country", sa.String(120)), sa.Column("timezone", sa.String(64), server_default="UTC", nullable=False),
        sa.Column("logo", sa.String(500)), sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("properties", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_properties_organization", "properties", "organizations", ["organization_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_properties_organization_id", "properties", ["organization_id"])
    for name, column in [
        ("type", sa.String(40)), ("city", sa.String(120)), ("state", sa.String(120)), ("country", sa.String(120)),
        ("phone", sa.String(40)), ("email", sa.String(255)), ("timezone", sa.String(64)),
        ("number_of_rooms", sa.Integer()), ("number_of_floors", sa.Integer()), ("operational_status", sa.String(20)),
    ]:
        kwargs = {"nullable": False, "server_default": "hotel" if name == "type" else "UTC" if name == "timezone" else "active"} if name in {"type", "timezone", "operational_status"} else {"nullable": True}
        op.add_column("properties", sa.Column(name, column, **kwargs))
    op.add_column("devices", sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_devices_property", "devices", "properties", ["property_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_devices_property_id", "devices", ["property_id"])


def downgrade():
    op.drop_index("ix_devices_property_id", table_name="devices")
    op.drop_constraint("fk_devices_property", "devices", type_="foreignkey")
    op.drop_column("devices", "property_id")
    for name in ["operational_status", "number_of_floors", "number_of_rooms", "timezone", "email", "phone", "country", "state", "city", "type"]:
        op.drop_column("properties", name)
    op.drop_index("ix_properties_organization_id", table_name="properties")
    op.drop_constraint("fk_properties_organization", "properties", type_="foreignkey")
    op.drop_column("properties", "organization_id")
    op.drop_table("organizations")
