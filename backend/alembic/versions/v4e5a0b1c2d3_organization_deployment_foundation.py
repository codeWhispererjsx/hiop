"""V4E.5 organization structure and passive local-agent foundation.

Revision ID: v4e5a0b1c2d3
Revises: v4e9f0a1b2c3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4e5a0b1c2d3"
down_revision = "v4e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("organizations", sa.Column("address", sa.String(500), nullable=True))
    op.add_column("organizations", sa.Column("description", sa.Text(), nullable=True))
    for table in ("buildings", "floors", "zones", "rooms", "departments"):
        op.add_column(table, sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_{table}_organization", table, "organizations", ["organization_id"], ["id"])
        op.create_index(f"ix_{table}_organization_id", table, ["organization_id"])
    op.execute("UPDATE buildings b SET organization_id=p.organization_id FROM properties p WHERE p.id=b.property_id AND b.organization_id IS NULL")
    op.execute("UPDATE floors f SET organization_id=b.organization_id FROM buildings b WHERE b.id=f.building_id AND f.organization_id IS NULL")
    op.execute("UPDATE zones z SET organization_id=f.organization_id FROM floors f WHERE f.id=z.floor_id AND z.organization_id IS NULL")
    op.execute("UPDATE rooms r SET organization_id=f.organization_id FROM floors f WHERE f.id=r.floor_id AND r.organization_id IS NULL")
    op.execute("UPDATE departments d SET organization_id=p.organization_id FROM properties p WHERE p.id=d.property_id AND d.organization_id IS NULL")
    for table in ("buildings", "floors", "zones", "rooms", "departments"):
        op.execute(f"UPDATE {table} SET organization_id=(SELECT id FROM organizations ORDER BY created_at LIMIT 1) WHERE organization_id IS NULL AND EXISTS (SELECT 1 FROM organizations)")
    for table in ("buildings", "floors", "zones", "rooms", "departments"):
        op.execute(f"DROP INDEX IF EXISTS uq_{table}_name_lower")
        op.execute(f"CREATE UNIQUE INDEX uq_{table}_org_name_lower ON {table} (organization_id, lower(name))")

    op.add_column("rooms", sa.Column("code", sa.String(40), nullable=True))
    op.add_column("rooms", sa.Column("type", sa.String(40), server_default="room", nullable=False))
    op.add_column("rooms", sa.Column("description", sa.String(255), nullable=True))
    op.add_column("rooms", sa.Column("status", sa.String(20), server_default="active", nullable=False))
    op.add_column("departments", sa.Column("code", sa.String(40), nullable=True))
    op.add_column("departments", sa.Column("description", sa.String(500), nullable=True))
    op.add_column("departments", sa.Column("status", sa.String(20), server_default="active", nullable=False))
    op.add_column("departments", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("departments", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_index("uq_department_org_code", "departments", ["organization_id", "code"], unique=True, postgresql_where=sa.text("code IS NOT NULL"))

    op.add_column("users", sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("users", sa.Column("primary_location_type", sa.String(30), nullable=True))
    op.add_column("users", sa.Column("primary_location_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_user_department", "users", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_users_department_id", "users", ["department_id"])
    op.create_index("ix_users_primary_location_id", "users", ["primary_location_id"])

    op.add_column("hospitality_technology_services", sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("hospitality_technology_services", sa.Column("location_type", sa.String(30), nullable=True))
    op.add_column("hospitality_technology_services", sa.Column("location_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_service_department", "hospitality_technology_services", "departments", ["department_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_services_department_id", "hospitality_technology_services", ["department_id"])
    op.create_index("ix_services_location_id", "hospitality_technology_services", ["location_id"])
    op.add_column("operational_incidents", sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_incident_room", "operational_incidents", "rooms", ["room_id"], ["id"])

    op.execute("CREATE SEQUENCE IF NOT EXISTS local_agent_number_seq START 1")
    op.create_table("local_agent_registrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", sa.String(40), nullable=False, unique=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("version", sa.String(50), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("registered_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint("status IN ('online','offline','unknown')", name="ck_local_agent_status"),
    )
    op.create_index("ix_local_agent_organization", "local_agent_registrations", ["organization_id"])
    op.create_index("uq_agent_org_name", "local_agent_registrations", ["organization_id", "name"], unique=True)


def downgrade():
    op.drop_table("local_agent_registrations")
    op.execute("DROP SEQUENCE IF EXISTS local_agent_number_seq")
    op.drop_constraint("fk_incident_room", "operational_incidents", type_="foreignkey")
    op.drop_column("operational_incidents", "room_id")
    for index in ("ix_services_location_id", "ix_services_department_id"):
        op.drop_index(index, table_name="hospitality_technology_services")
    op.drop_constraint("fk_service_department", "hospitality_technology_services", type_="foreignkey")
    for column in ("location_id", "location_type", "department_id"):
        op.drop_column("hospitality_technology_services", column)
    for index in ("ix_users_primary_location_id", "ix_users_department_id"):
        op.drop_index(index, table_name="users")
    op.drop_constraint("fk_user_department", "users", type_="foreignkey")
    for column in ("primary_location_id", "primary_location_type", "department_id"):
        op.drop_column("users", column)
    op.drop_index("uq_department_org_code", table_name="departments")
    for column in ("updated_at", "created_at", "status", "description", "code"):
        op.drop_column("departments", column)
    for column in ("status", "description", "type", "code"):
        op.drop_column("rooms", column)
    for table in ("departments", "rooms", "zones", "floors", "buildings"):
        op.drop_index(f"uq_{table}_org_name_lower", table_name=table)
        op.create_index(f"uq_{table}_name_lower", table, [sa.text("lower(name)")], unique=True)
        op.drop_index(f"ix_{table}_organization_id", table_name=table)
        op.drop_constraint(f"fk_{table}_organization", table, type_="foreignkey")
        op.drop_column(table, "organization_id")
    op.drop_column("organizations", "description")
    op.drop_column("organizations", "address")
