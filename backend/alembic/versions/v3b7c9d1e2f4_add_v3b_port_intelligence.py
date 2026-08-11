"""add V3B switch and port intelligence

Revision ID: v3b7c9d1e2f4
Revises: 9f1a2b3c4d70
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v3b7c9d1e2f4"
down_revision = "9f1a2b3c4d70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("snmp_interfaces", sa.Column("duplex", sa.String(20)))
    op.create_table(
        "port_device_associations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("switch_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interface_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_interfaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connected_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("topology_link_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("topology_links.id", ondelete="SET NULL")),
        sa.Column("observed_mac", sa.String(17)),
        sa.Column("association_type", sa.String(20), nullable=False, server_default="endpoint"),
        sa.Column("evidence_source", sa.String(40), nullable=False, server_default="SNMP_MAC_TABLE"),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_level", sa.String(10), nullable=False, server_default="low"),
        sa.Column("confidence_explanation", sa.String(500), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_port_device_association_confidence"),
        sa.UniqueConstraint("interface_id", "observed_mac", "connected_device_id", name="uq_port_device_association_identity"),
    )
    op.create_index("ix_port_associations_switch_current", "port_device_associations", ["switch_device_id", "is_current"])
    op.create_index("ix_port_associations_device_current", "port_device_associations", ["connected_device_id", "is_current"])
    op.create_index("ix_port_associations_interface_current", "port_device_associations", ["interface_id", "is_current"])
    op.create_index("ix_port_associations_mac", "port_device_associations", ["observed_mac"])


def downgrade() -> None:
    op.drop_table("port_device_associations")
    op.drop_column("snmp_interfaces", "duplex")
