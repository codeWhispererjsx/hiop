"""Add import matching and location suggestion persistence.

Revision ID: 91b7d3e5a204
Revises: 2c6a8e4f901b
Create Date: 2026-07-20
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "91b7d3e5a204"
down_revision = "2c6a8e4f901b"
branch_labels = None
depends_on = None


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True)


def upgrade() -> None:
    op.add_column("import_sessions", sa.Column("matching_state", sa.String(16), server_default="idle", nullable=False))
    op.add_column("import_sessions", sa.Column("match_summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_check_constraint("ck_import_sessions_matching_state", "import_sessions", "matching_state IN ('idle', 'running', 'completed', 'failed')")
    for name, column in (
        ("resolution_action", sa.String(32)),
        ("linked_device_id", postgresql.UUID(as_uuid=True)),
        ("linked_discovery_id", postgresql.UUID(as_uuid=True)),
        ("resolved_by", sa.String()),
        ("resolved_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("imported_devices", sa.Column(name, column))
    op.create_foreign_key("fk_imported_devices_linked_device", "imported_devices", "devices", ["linked_device_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_imported_devices_linked_discovery", "imported_devices", "discovered_devices", ["linked_discovery_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_imported_devices_resolved_by", "imported_devices", "users", ["resolved_by"], ["id"], ondelete="SET NULL")

    op.create_table(
        "import_match_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("imported_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("candidate_type", _enum("import_candidate_type", "inventory_device", "discovered_device", "imported_device"), nullable=False),
        sa.Column("candidate_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="CASCADE")),
        sa.Column("candidate_discovery_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovered_devices.id", ondelete="CASCADE")),
        sa.Column("candidate_imported_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_devices.id", ondelete="CASCADE")),
        sa.Column("match_score", sa.Integer(), nullable=False),
        sa.Column("match_level", _enum("import_match_level", "exact", "strong", "probable", "weak", "none"), nullable=False),
        sa.Column("match_status", _enum("import_match_status", "pending", "accepted", "rejected", "resolved", "ignored"), server_default="pending", nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("conflicting_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("matching_fields", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("recommended_action", _enum("import_recommended_action", "link", "merge", "create_new", "review", "skip"), nullable=False),
        sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("match_score >= 0 AND match_score <= 100", name="ck_import_match_candidates_score"),
        sa.CheckConstraint("num_nonnulls(candidate_device_id, candidate_discovery_id, candidate_imported_device_id) = 1", name="ck_import_match_candidates_one_target"),
    )
    op.create_index("ix_import_match_candidates_session_rank", "import_match_candidates", ["import_session_id", "match_score"])
    op.create_index("ix_import_match_candidates_imported_device", "import_match_candidates", ["imported_device_id"])
    op.create_index("ix_import_match_candidates_status", "import_match_candidates", ["match_status"])
    op.create_index("uq_import_match_candidate_inventory", "import_match_candidates", ["imported_device_id", "candidate_device_id"], unique=True)
    op.create_index("uq_import_match_candidate_discovery", "import_match_candidates", ["imported_device_id", "candidate_discovery_id"], unique=True)
    op.create_index("uq_import_match_candidate_imported", "import_match_candidates", ["imported_device_id", "candidate_imported_device_id"], unique=True)

    op.create_table(
        "import_location_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("imported_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("departments.id", ondelete="SET NULL")),
        sa.Column("building_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("buildings.id", ondelete="SET NULL")),
        sa.Column("floor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("floors.id", ondelete="SET NULL")),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("rooms.id", ondelete="SET NULL")),
        sa.Column("network_zone_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("network_zones.id", ondelete="SET NULL")),
        sa.Column("confidence_score", sa.Integer(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("conflicts", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("status", _enum("import_location_suggestion_status", "pending", "accepted", "rejected", "overridden"), server_default="pending", nullable=False),
        sa.Column("reviewed_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("confidence_score >= 0 AND confidence_score <= 100", name="ck_import_location_suggestions_score"),
    )
    op.create_index("uq_import_location_suggestions_imported_device", "import_location_suggestions", ["imported_device_id"], unique=True)
    op.create_index("ix_import_location_suggestions_status", "import_location_suggestions", ["status"])


def downgrade() -> None:
    op.drop_table("import_location_suggestions")
    op.drop_table("import_match_candidates")
    op.drop_constraint("fk_imported_devices_resolved_by", "imported_devices", type_="foreignkey")
    op.drop_constraint("fk_imported_devices_linked_discovery", "imported_devices", type_="foreignkey")
    op.drop_constraint("fk_imported_devices_linked_device", "imported_devices", type_="foreignkey")
    for column in ("resolved_at", "resolved_by", "linked_discovery_id", "linked_device_id", "resolution_action"):
        op.drop_column("imported_devices", column)
    op.drop_constraint("ck_import_sessions_matching_state", "import_sessions", type_="check")
    op.drop_column("import_sessions", "match_summary")
    op.drop_column("import_sessions", "matching_state")
