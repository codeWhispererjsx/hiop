"""Add SNMP target polling health metadata.

Revision ID: d2f6b8c4a901
Revises: c9e4a7b2d610
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d2f6b8c4a901"
down_revision = "c9e4a7b2d610"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE snmp_metrics SET quality = 'warning' WHERE quality = 'unknown'")
    op.alter_column("snmp_metrics", "quality", server_default="warning")
    op.add_column("snmp_targets", sa.Column("last_response_time_ms", sa.Float()))
    op.add_column("snmp_targets", sa.Column("detected_sys_object_id", sa.String(255)))
    op.add_column("snmp_targets", sa.Column("detected_profile_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_snmp_target_detected_profile", "snmp_targets", "snmp_device_profiles", ["detected_profile_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_snmp_targets_detected_profile_id", "snmp_targets", ["detected_profile_id"])


def downgrade():
    op.alter_column("snmp_metrics", "quality", server_default="unknown")
    op.execute("UPDATE snmp_metrics SET quality = 'unknown' WHERE quality = 'warning'")
    op.drop_index("ix_snmp_targets_detected_profile_id", table_name="snmp_targets")
    op.drop_constraint("fk_snmp_target_detected_profile", "snmp_targets", type_="foreignkey")
    op.drop_column("snmp_targets", "detected_profile_id")
    op.drop_column("snmp_targets", "detected_sys_object_id")
    op.drop_column("snmp_targets", "last_response_time_ms")
