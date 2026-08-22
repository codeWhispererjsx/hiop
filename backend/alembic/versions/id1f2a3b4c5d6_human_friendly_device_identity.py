"""Human-friendly device identity and scoped naming rules.

Revision ID: id1f2a3b4c5d6
Revises: saas1a2b3c4d5
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "id1f2a3b4c5d6"
down_revision = "saas1a2b3c4d5"
branch_labels = None
depends_on = None
u = postgresql.UUID(as_uuid=True)


def upgrade():
    op.create_table(
        "discovery_identity_profiles",
        sa.Column("id", u, primary_key=True),
        sa.Column("result_id", u, sa.ForeignKey("enterprise_discovery_results.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("organization_id", u, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", u, sa.ForeignKey("properties.id", ondelete="CASCADE")),
        sa.Column("friendly_name_source", sa.String(20)), sa.Column("friendly_name_confidence", sa.Integer()),
        sa.Column("classification_source", sa.String(30)), sa.Column("classification_confidence", sa.Integer()),
        sa.Column("department_source", sa.String(30)), sa.Column("location_source", sa.String(30)),
        sa.Column("identity_sequence", sa.Integer()), sa.Column("suggestion", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("friendly_name_confidence IS NULL OR friendly_name_confidence BETWEEN 0 AND 100", name="ck_identity_profile_friendly_confidence"),
        sa.CheckConstraint("classification_confidence IS NULL OR classification_confidence BETWEEN 0 AND 100", name="ck_identity_profile_classification_confidence"),
    )
    for name in ("result_id", "organization_id", "property_id"):
        op.create_index(f"ix_discovery_identity_profiles_{name}", "discovery_identity_profiles", [name])
    op.create_index("ix_identity_profile_property_source", "discovery_identity_profiles", ["property_id", "friendly_name_source"])

    op.create_table(
        "discovery_identity_rules",
        sa.Column("id", u, primary_key=True),
        sa.Column("organization_id", u, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", u, sa.ForeignKey("properties.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("match_field", sa.String(30), nullable=False),
        sa.Column("match_operator", sa.String(20), nullable=False),
        sa.Column("pattern", sa.String(255), nullable=False),
        sa.Column("output_device_type", sa.String(80)),
        sa.Column("output_department_id", u, sa.ForeignKey("departments.id", ondelete="SET NULL")),
        sa.Column("output_location", sa.String(160)),
        sa.Column("friendly_name_template", sa.String(255), nullable=False, server_default="{department} {device_type} {sequence}"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("confidence", sa.Integer(), nullable=False, server_default="70"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("match_field IN ('hostname','fqdn','vendor','snmp','ad_ou','device_type')", name="ck_identity_rule_match_field"),
        sa.CheckConstraint("match_operator IN ('contains','starts_with','ends_with','equals')", name="ck_identity_rule_match_operator"),
        sa.CheckConstraint("confidence BETWEEN 1 AND 100", name="ck_identity_rule_confidence"),
        sa.UniqueConstraint("organization_id", "property_id", "name", name="uq_identity_rule_scope_name"),
    )
    for name in ("organization_id", "property_id", "output_department_id"):
        op.create_index(f"ix_discovery_identity_rules_{name}", "discovery_identity_rules", [name])
    op.create_index("ix_identity_rule_scope_enabled", "discovery_identity_rules", ["organization_id", "property_id", "enabled"])


def downgrade():
    op.drop_table("discovery_identity_rules")
    op.drop_table("discovery_identity_profiles")
