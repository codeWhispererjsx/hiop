"""V2C read-only Active Directory intelligence fields.

Revision ID: 8b9c0d1e2f36
Revises: 7a8b9c0d1e25
"""
from alembic import op
import sqlalchemy as sa

revision="8b9c0d1e2f36";down_revision="7a8b9c0d1e25";branch_labels=None;depends_on=None

def upgrade():
    for column in (
        sa.Column("suggested_department",sa.String(120)),sa.Column("ad_computer_name",sa.String(255)),
        sa.Column("ad_distinguished_name",sa.String(512)),sa.Column("ad_domain",sa.String(255)),
        sa.Column("ad_organizational_unit",sa.String(255)),sa.Column("ad_description",sa.Text()),
        sa.Column("ad_operating_system",sa.String(255)),sa.Column("ad_operating_system_version",sa.String(255)),
        sa.Column("ad_enabled",sa.Boolean()),sa.Column("ad_last_logon_at",sa.DateTime(timezone=True)),
        sa.Column("ad_enrichment_status",sa.String(40),nullable=False,server_default="not_attempted"),
        sa.Column("ad_last_error",sa.String(80)),sa.Column("ad_last_enriched_at",sa.DateTime(timezone=True)),
    ):op.add_column("enterprise_discovery_results",column)
    op.create_check_constraint("ck_discovery_result_ad_status","enterprise_discovery_results","ad_enrichment_status IN ('not_attempted','attempted','enriched','partially_enriched','unavailable')")
    for column in (
        sa.Column("ad_computer_name",sa.String(255)),sa.Column("ad_distinguished_name",sa.String(512)),
        sa.Column("ad_domain",sa.String(255)),sa.Column("ad_organizational_unit",sa.String(255)),
        sa.Column("ad_operating_system",sa.String(255)),sa.Column("ad_operating_system_version",sa.String(255)),
        sa.Column("ad_enabled",sa.Boolean()),sa.Column("ad_last_logon_at",sa.DateTime(timezone=True)),
    ):op.add_column("devices",column)

def downgrade():
    for name in ("ad_last_logon_at","ad_enabled","ad_operating_system_version","ad_operating_system","ad_organizational_unit","ad_domain","ad_distinguished_name","ad_computer_name"):op.drop_column("devices",name)
    op.drop_constraint("ck_discovery_result_ad_status","enterprise_discovery_results",type_="check")
    for name in ("ad_last_enriched_at","ad_last_error","ad_enrichment_status","ad_last_logon_at","ad_enabled","ad_operating_system_version","ad_operating_system","ad_description","ad_organizational_unit","ad_domain","ad_distinguished_name","ad_computer_name","suggested_department"):op.drop_column("enterprise_discovery_results",name)
