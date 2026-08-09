"""V2B SNMP device enrichment fields.

Revision ID: 7a8b9c0d1e25
Revises: 6a7b8c9d0e14
"""
from alembic import op
import sqlalchemy as sa

revision="7a8b9c0d1e25";down_revision="6a7b8c9d0e14";branch_labels=None;depends_on=None

def upgrade():
    for column in (
        sa.Column("model",sa.String(180)),sa.Column("serial_number",sa.String(180)),sa.Column("firmware",sa.String(180)),
        sa.Column("sys_description",sa.Text()),sa.Column("sys_object_id",sa.String(255)),sa.Column("uptime_seconds",sa.Float()),
        sa.Column("interface_count",sa.Integer()),sa.Column("interface_information",sa.Text(),nullable=False,server_default="[]"),
        sa.Column("snmp_enrichment_status",sa.String(40),nullable=False,server_default="not_attempted"),
        sa.Column("snmp_last_error",sa.String(80)),sa.Column("last_enriched_at",sa.DateTime(timezone=True)),
    ):op.add_column("enterprise_discovery_results",column)
    op.create_check_constraint("ck_discovery_result_snmp_status","enterprise_discovery_results","snmp_enrichment_status IN ('not_attempted','attempted','enriched','partially_enriched','unavailable')")

def downgrade():
    op.drop_constraint("ck_discovery_result_snmp_status","enterprise_discovery_results",type_="check")
    for name in ("last_enriched_at","snmp_last_error","snmp_enrichment_status","interface_information","interface_count","uptime_seconds","sys_object_id","sys_description","firmware","serial_number","model"):op.drop_column("enterprise_discovery_results",name)
