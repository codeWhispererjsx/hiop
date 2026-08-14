"""V4E operational service and incident management.

Revision ID: v4e9f0a1b2c3
Revises: v4d8e9f0a1b2
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4e9f0a1b2c3"
down_revision = "v4d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hospitality_technology_services", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("hospitality_technology_services", sa.Column("owner_team", sa.String(160), nullable=True))
    op.add_column("hospitality_technology_services", sa.Column("owner_user_id", sa.String(), nullable=True))
    op.add_column("hospitality_technology_services", sa.Column("notes", sa.String(4000), nullable=True))
    op.add_column("hospitality_technology_services", sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.add_column("hospitality_technology_services", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_foreign_key("fk_service_organization", "hospitality_technology_services", "organizations", ["organization_id"], ["id"])
    op.create_foreign_key("fk_service_owner_user", "hospitality_technology_services", "users", ["owner_user_id"], ["id"])
    op.create_index("ix_service_organization", "hospitality_technology_services", ["organization_id"])
    op.execute("UPDATE hospitality_technology_services s SET organization_id=p.organization_id FROM properties p WHERE p.id=s.property_id AND s.organization_id IS NULL")

    for name, column in (
        ("asset_id", sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=True)),
        ("category", sa.Column("category", sa.String(40), server_default="other", nullable=False)),
        ("assigned_team", sa.Column("assigned_team", sa.String(160), nullable=True)),
        ("assigned_technician_id", sa.Column("assigned_technician_id", sa.String(), nullable=True)),
        ("requester_id", sa.Column("requester_id", sa.String(), nullable=True)),
        ("resolution_summary", sa.Column("resolution_summary", sa.Text(), nullable=True)),
        ("root_cause_notes", sa.Column("root_cause_notes", sa.Text(), nullable=True)),
        ("follow_up_notes", sa.Column("follow_up_notes", sa.Text(), nullable=True)),
        ("closure_notes", sa.Column("closure_notes", sa.Text(), nullable=True)),
    ):
        op.add_column("operational_incidents", column)
    op.create_foreign_key("fk_incident_asset", "operational_incidents", "managed_assets", ["asset_id"], ["id"])
    op.create_foreign_key("fk_incident_assigned_technician", "operational_incidents", "users", ["assigned_technician_id"], ["id"])
    op.create_foreign_key("fk_incident_requester", "operational_incidents", "users", ["requester_id"], ["id"])
    op.create_foreign_key("fk_incident_service", "operational_incidents", "hospitality_technology_services", ["technology_service_id"], ["id"])
    op.create_index("ix_incident_asset_id", "operational_incidents", ["asset_id"])
    op.create_index("ix_incident_category", "operational_incidents", ["category"])
    op.create_index("ix_incident_assigned_technician", "operational_incidents", ["assigned_technician_id"])

    op.create_table("service_asset_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hospitality_technology_services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(30), server_default="supports", nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("uq_service_asset_relationship", "service_asset_relationships", ["service_id", "asset_id"], unique=True)
    op.create_index("ix_service_asset_org", "service_asset_relationships", ["organization_id"])
    op.create_table("incident_asset_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("operational_incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("managed_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship_type", sa.String(30), server_default="affected", nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("uq_incident_asset_relationship", "incident_asset_relationships", ["incident_id", "asset_id"], unique=True)
    op.create_index("ix_incident_asset_org", "incident_asset_relationships", ["organization_id"])


def downgrade():
    op.drop_table("incident_asset_relationships")
    op.drop_table("service_asset_relationships")
    for index in ("ix_incident_assigned_technician", "ix_incident_category", "ix_incident_asset_id"):
        op.drop_index(index, table_name="operational_incidents")
    for constraint in ("fk_incident_service", "fk_incident_requester", "fk_incident_assigned_technician", "fk_incident_asset"):
        op.drop_constraint(constraint, "operational_incidents", type_="foreignkey")
    for column in ("closure_notes", "follow_up_notes", "root_cause_notes", "resolution_summary", "requester_id", "assigned_technician_id", "assigned_team", "category", "asset_id"):
        op.drop_column("operational_incidents", column)
    op.drop_index("ix_service_organization", table_name="hospitality_technology_services")
    op.drop_constraint("fk_service_owner_user", "hospitality_technology_services", type_="foreignkey")
    op.drop_constraint("fk_service_organization", "hospitality_technology_services", type_="foreignkey")
    for column in ("updated_at", "created_at", "notes", "owner_user_id", "owner_team", "organization_id"):
        op.drop_column("hospitality_technology_services", column)
