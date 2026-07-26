"""add topology neighbor discovery

Revision ID: e1d3f5a7b902
Revises: d0c2bcea6dda
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e1d3f5a7b902"
down_revision: Union[str, Sequence[str], None] = "d0c2bcea6dda"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topology_neighbor_collection_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("protocols_requested", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("protocols_completed", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("local_ports_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_neighbors_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("normalized_neighbors", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidate_nodes_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidate_links_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("candidate_links_updated", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conflicts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("trigger_type", sa.String(20), server_default="manual", nullable=False),
        sa.Column("triggered_by", sa.String()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("error_category", sa.String(40)),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("cancellation_requested", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["snmp_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_neighbor_runs_topology_status_started", "topology_neighbor_collection_runs", ["topology_id", "status", "started_at"])
    op.create_index("ix_neighbor_runs_target_started", "topology_neighbor_collection_runs", ["target_id", "started_at"])

    op.create_table(
        "topology_neighbor_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("collection_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_device_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source_interface_id", postgresql.UUID(as_uuid=True)),
        sa.Column("protocol", sa.String(8), nullable=False),
        sa.Column("local_port_identifier", sa.String(255), nullable=False),
        sa.Column("local_port_description", sa.String(500)),
        sa.Column("remote_identity_key", sa.String(300), nullable=False),
        sa.Column("remote_chassis_id", sa.String(255)),
        sa.Column("remote_chassis_subtype", sa.String(40)),
        sa.Column("remote_port_id", sa.String(255)),
        sa.Column("remote_port_subtype", sa.String(40)),
        sa.Column("remote_port_description", sa.String(500)),
        sa.Column("remote_system_name", sa.String(255)),
        sa.Column("remote_system_description", sa.String(1000)),
        sa.Column("remote_management_address", sa.String(45)),
        sa.Column("remote_capabilities", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("remote_platform", sa.String(255)),
        sa.Column("native_vlan", sa.Integer()),
        sa.Column("duplex", sa.String(20)),
        sa.Column("raw_index", sa.String(255)),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("observation_status", sa.String(20), server_default="current", nullable=False),
        sa.Column("missing_collections", sa.Integer(), server_default="0", nullable=False),
        sa.Column("normalized_identity", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["collection_run_id"], ["topology_neighbor_collection_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_target_id"], ["snmp_targets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_node_id"], ["topology_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_interface_id"], ["snmp_interfaces.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("topology_id", "source_target_id", "protocol", "local_port_identifier", "remote_identity_key", name="uq_neighbor_observation_identity"),
    )
    op.create_index("ix_neighbor_observations_topology_status", "topology_neighbor_observations", ["topology_id", "observation_status"])
    op.create_index("ix_neighbor_observations_target_protocol", "topology_neighbor_observations", ["source_target_id", "protocol"])
    op.create_index("ix_neighbor_observations_remote_identity", "topology_neighbor_observations", ["remote_identity_key"])
    op.create_index("ix_neighbor_observations_last_seen", "topology_neighbor_observations", ["last_seen_at"])

    op.create_table(
        "topology_neighbor_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_observation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("remote_identity_key", sa.String(300), nullable=False),
        sa.Column("remote_chassis_id", sa.String(255)),
        sa.Column("remote_system_name", sa.String(255)),
        sa.Column("remote_management_address", sa.String(45)),
        sa.Column("remote_port_id", sa.String(255)),
        sa.Column("vendor_guess", sa.String(120)),
        sa.Column("device_type_guess", sa.String(40), server_default="unknown", nullable=False),
        sa.Column("matched_device_id", postgresql.UUID(as_uuid=True)),
        sa.Column("matched_discovered_device_id", postgresql.UUID(as_uuid=True)),
        sa.Column("matched_snmp_target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("matched_topology_node_id", postgresql.UUID(as_uuid=True)),
        sa.Column("confidence_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("score_breakdown", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("conflict_flags", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("review_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_neighbor_candidate_confidence"),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_observation_id"], ["topology_neighbor_observations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_discovered_device_id"], ["discovered_devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_snmp_target_id"], ["snmp_targets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["matched_topology_node_id"], ["topology_nodes.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("topology_id", "remote_identity_key", name="uq_neighbor_candidate_identity"),
    )
    op.create_index("ix_neighbor_candidates_topology_review", "topology_neighbor_candidates", ["topology_id", "review_status"])
    op.create_index("ix_neighbor_candidates_management_address", "topology_neighbor_candidates", ["remote_management_address"])


def downgrade() -> None:
    op.drop_table("topology_neighbor_candidates")
    op.drop_table("topology_neighbor_observations")
    op.drop_table("topology_neighbor_collection_runs")
