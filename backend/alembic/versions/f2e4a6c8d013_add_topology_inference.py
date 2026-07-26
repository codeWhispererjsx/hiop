"""add topology inference and review

Revision ID: f2e4a6c8d013
Revises: e1d3f5a7b902
Create Date: 2026-07-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f2e4a6c8d013"
down_revision: Union[str, Sequence[str], None] = "e1d3f5a7b902"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "topology_inference_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("triggered_by", sa.String()),
        sa.Column("dry_run", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("nodes_analyzed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("links_analyzed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("links_merged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("node_recommendations", sa.Integer(), server_default="0", nullable=False),
        sa.Column("dependencies_inferred", sa.Integer(), server_default="0", nullable=False),
        sa.Column("conflicts_detected", sa.Integer(), server_default="0", nullable=False),
        sa.Column("review_items_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("graph_checksum_before", sa.String(64)),
        sa.Column("graph_checksum_after", sa.String(64)),
        sa.Column("summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_summary", sa.String(500)),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_topology_inference_runs_topology_status", "topology_inference_runs", ["topology_id", "status", "started_at"])

    op.create_table(
        "topology_conflicts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inference_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("conflict_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("related_entity_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("confidence_score", sa.Integer(), server_default="0", nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("suggested_resolution", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), server_default="open", nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String()),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inference_run_id"], ["topology_inference_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_topology_conflicts_topology_status", "topology_conflicts", ["topology_id", "status", "severity"])
    op.create_index("ix_topology_conflicts_entity", "topology_conflicts", ["entity_type", "entity_id"])

    op.create_table(
        "topology_review_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inference_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("review_type", sa.String(40), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("proposed_change", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("impact", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("reviewed_by", sa.String()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_note", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_topology_review_confidence"),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inference_run_id"], ["topology_inference_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_topology_review_items_topology_status", "topology_review_items", ["topology_id", "status", "created_at"])

    op.create_table(
        "topology_confidence_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("topology_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inference_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("previous_score", sa.Integer()),
        sa.Column("calculated_score", sa.Integer(), nullable=False),
        sa.Column("contributions", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["topology_id"], ["topologies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inference_run_id"], ["topology_inference_runs.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_topology_confidence_entity_time", "topology_confidence_history", ["topology_id", "entity_type", "entity_id", "calculated_at"])


def downgrade() -> None:
    op.drop_table("topology_confidence_history")
    op.drop_table("topology_review_items")
    op.drop_table("topology_conflicts")
    op.drop_table("topology_inference_runs")
