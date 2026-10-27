"""bind enrolled agents to their managed device

Revision ID: v2fagentact01
Revises: v2eapproval01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2fagentact01"
down_revision = "v2eapproval01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "local_agent_registrations",
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_local_agent_device",
        "local_agent_registrations",
        "devices",
        ["device_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_local_agent_registrations_device_id",
        "local_agent_registrations",
        ["device_id"],
    )


def downgrade():
    op.drop_index("ix_local_agent_registrations_device_id", table_name="local_agent_registrations")
    op.drop_constraint("fk_local_agent_device", "local_agent_registrations", type_="foreignkey")
    op.drop_column("local_agent_registrations", "device_id")
