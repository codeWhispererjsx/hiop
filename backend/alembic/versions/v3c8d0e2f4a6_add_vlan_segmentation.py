"""add V3C VLAN segmentation intelligence

Revision ID: v3c8d0e2f4a6
Revises: v3b7c9d1e2f4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v3c8d0e2f4a6"
down_revision = "v3b7c9d1e2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("network_segments", "cidr", existing_type=sa.String(64), nullable=True)
    op.add_column("network_segments", sa.Column("vlan_status", sa.String(20), nullable=False, server_default="unknown"))
    op.add_column("network_segments", sa.Column("gateway", sa.String(64)))
    op.add_column("network_segments", sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("network_segments", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.add_column("network_segments", sa.Column("stale_at", sa.DateTime(timezone=True)))
    op.create_index("uq_topology_vlan_id", "network_segments", ["topology_id", "vlan_id"], unique=True, postgresql_where=sa.text("vlan_id IS NOT NULL"))
    op.create_table(
        "vlan_membership_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("network_segment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("network_segments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("switch_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("interface_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("snmp_interfaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connected_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("port_association_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("port_device_associations.id", ondelete="SET NULL")),
        sa.Column("membership_type", sa.String(20), nullable=False),
        sa.Column("port_mode", sa.String(10), nullable=False, server_default="unknown"),
        sa.Column("evidence_source", sa.String(40), nullable=False, server_default="SNMP_Q_BRIDGE"),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("confidence_explanation", sa.String(500), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("stale_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_vlan_membership_confidence"),
        sa.UniqueConstraint("network_segment_id", "interface_id", "connected_device_id", "membership_type", name="uq_vlan_membership_identity"),
    )
    op.create_index("ix_vlan_membership_device_current", "vlan_membership_observations", ["connected_device_id", "is_current"])
    op.create_index("ix_vlan_membership_switch_current", "vlan_membership_observations", ["switch_device_id", "is_current"])
    op.create_index("ix_vlan_membership_interface_current", "vlan_membership_observations", ["interface_id", "is_current"])


def downgrade() -> None:
    op.drop_table("vlan_membership_observations")
    op.drop_index("uq_topology_vlan_id", table_name="network_segments")
    for column in ("stale_at", "last_seen_at", "first_seen_at", "gateway", "vlan_status"):
        op.drop_column("network_segments", column)
    op.alter_column("network_segments", "cidr", existing_type=sa.String(64), nullable=False)
