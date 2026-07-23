"""Add AD matching, mapping, links, and reconciliation results.

Revision ID: b8d4f6a10235
Revises: a7c3e5f90124
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "b8d4f6a10235"
down_revision = "a7c3e5f90124"
branch_labels = None
depends_on = None


def _audit_columns():
    return [
        sa.Column("priority", sa.Integer(), server_default="100", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
    ]


def upgrade() -> None:
    op.drop_constraint("uq_ad_candidate_target", "active_directory_match_candidates", type_="unique")
    op.drop_constraint("ck_ad_candidate_typed_target", "active_directory_match_candidates", type_="check")
    op.drop_constraint("ck_ad_candidate_level", "active_directory_match_candidates", type_="check")
    op.drop_constraint("ck_ad_candidate_status", "active_directory_match_candidates", type_="check")
    op.drop_constraint("ck_ad_candidate_action", "active_directory_match_candidates", type_="check")
    op.add_column("active_directory_match_candidates", sa.Column("candidate_discovery_id", postgresql.UUID(as_uuid=True)))
    op.add_column("active_directory_match_candidates", sa.Column("candidate_department_id", postgresql.UUID(as_uuid=True)))
    op.add_column("active_directory_match_candidates", sa.Column("candidate_role_id", sa.String(30)))
    op.add_column("active_directory_match_candidates", sa.Column("source_version", sa.DateTime(timezone=True)))
    op.add_column("active_directory_match_candidates", sa.Column("target_version", sa.DateTime(timezone=True)))
    op.create_foreign_key("fk_ad_candidate_discovery", "active_directory_match_candidates", "discovered_devices", ["candidate_discovery_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_ad_candidate_department", "active_directory_match_candidates", "departments", ["candidate_department_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_ad_candidates_candidate_discovery_id", "active_directory_match_candidates", ["candidate_discovery_id"])
    op.create_index("ix_ad_candidates_candidate_department_id", "active_directory_match_candidates", ["candidate_department_id"])
    op.execute("UPDATE active_directory_match_candidates SET match_level = CASE match_level WHEN 'high' THEN 'strong' WHEN 'medium' THEN 'probable' WHEN 'low' THEN 'weak' ELSE match_level END")
    op.execute("UPDATE active_directory_match_candidates SET match_status = 'resolved' WHERE match_status = 'auto_matched'")
    op.create_check_constraint("ck_ad_candidate_typed_target", "active_directory_match_candidates",
        "(candidate_type = 'hiop_user' AND candidate_user_id IS NOT NULL) OR "
        "(candidate_type = 'hiop_device' AND candidate_device_id IS NOT NULL) OR "
        "(candidate_type = 'discovered_device' AND candidate_discovery_id IS NOT NULL) OR "
        "(candidate_type = 'department' AND candidate_department_id IS NOT NULL) OR "
        "(candidate_type = 'role' AND candidate_role_id IS NOT NULL)")
    op.create_check_constraint("ck_ad_candidate_level", "active_directory_match_candidates", "match_level IN ('exact','strong','probable','weak','none')")
    op.create_check_constraint("ck_ad_candidate_status", "active_directory_match_candidates", "match_status IN ('pending','accepted','rejected','ignored','resolved')")
    op.create_check_constraint("ck_ad_candidate_action", "active_directory_match_candidates", "recommended_action IN ('link','create','enrich','review','ignore','disable_review','conflict')")

    op.create_table(
        "active_directory_record_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("directory_object_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(), nullable=True),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("discovery_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("linked_by", sa.String(), nullable=True),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("source_version", sa.DateTime(timezone=True)),
        sa.CheckConstraint("(user_id IS NOT NULL AND device_id IS NULL) OR (user_id IS NULL AND device_id IS NOT NULL)", name="ck_ad_record_link_single_target"),
        sa.ForeignKeyConstraint(["connection_id"], ["active_directory_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["directory_object_id"], ["active_directory_objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["discovery_id"], ["discovered_devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["linked_by"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("directory_object_id", name="uq_ad_record_link_object"),
        sa.UniqueConstraint("connection_id", "user_id", name="uq_ad_record_link_user"),
        sa.UniqueConstraint("connection_id", "device_id", name="uq_ad_record_link_device"),
    )
    op.create_index("ix_ad_record_links_connection_id", "active_directory_record_links", ["connection_id"])

    op.create_table(
        "active_directory_department_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("source_value", sa.String(255), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["connection_id"], ["active_directory_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("connection_id", "source_value", name="uq_ad_department_mapping_source"),
    )
    op.create_index("ix_ad_department_mappings_connection_id", "active_directory_department_mappings", ["connection_id"])
    op.create_table(
        "active_directory_ou_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("pattern", sa.String(255), nullable=False),
        sa.Column("department_id", postgresql.UUID(as_uuid=True)),
        sa.Column("building_id", postgresql.UUID(as_uuid=True)),
        sa.Column("floor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("room_id", postgresql.UUID(as_uuid=True)),
        sa.Column("network_zone_id", postgresql.UUID(as_uuid=True)),
        sa.Column("device_category", sa.String(80)),
        sa.Column("user_category", sa.String(80)),
        *_audit_columns(),
        sa.ForeignKeyConstraint(["connection_id"], ["active_directory_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["floor_id"], ["floors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["network_zone_id"], ["network_zones.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("connection_id", "pattern", "priority", name="uq_ad_ou_mapping_rule"),
    )
    op.create_index("ix_ad_ou_mappings_connection_id", "active_directory_ou_mappings", ["connection_id"])
    op.create_table(
        "active_directory_group_role_mappings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("source_group", sa.String(255), nullable=False),
        sa.Column("target_role", sa.String(30), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint("target_role IN ('admin','technician','staff')", name="ck_ad_group_role_target"),
        sa.ForeignKeyConstraint(["connection_id"], ["active_directory_connections.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("connection_id", "source_group", name="uq_ad_group_role_mapping_source"),
    )
    op.create_index("ix_ad_group_role_mappings_connection_id", "active_directory_group_role_mappings", ["connection_id"])
    op.create_table(
        "active_directory_reconciliation_results",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("directory_object_id", sa.String(36), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("target_user_id", sa.String()),
        sa.Column("target_device_id", postgresql.UUID(as_uuid=True)),
        sa.Column("before_values", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("after_values", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("safe_error", sa.String(500)),
        sa.Column("retryable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("reviewed_by", sa.String()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["directory_object_id"], ["active_directory_objects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_device_id"], ["devices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_ad_reconciliation_results_object_id", "active_directory_reconciliation_results", ["directory_object_id"])
    op.create_index("ix_ad_reconciliation_results_status", "active_directory_reconciliation_results", ["status"])


def downgrade() -> None:
    for table, indexes in (
        ("active_directory_reconciliation_results", ["ix_ad_reconciliation_results_status", "ix_ad_reconciliation_results_object_id"]),
        ("active_directory_group_role_mappings", ["ix_ad_group_role_mappings_connection_id"]),
        ("active_directory_ou_mappings", ["ix_ad_ou_mappings_connection_id"]),
        ("active_directory_department_mappings", ["ix_ad_department_mappings_connection_id"]),
        ("active_directory_record_links", ["ix_ad_record_links_connection_id"]),
    ):
        for index in indexes:
            op.drop_index(index, table_name=table)
        op.drop_table(table)
    op.drop_constraint("ck_ad_candidate_action", "active_directory_match_candidates", type_="check")
    op.drop_constraint("ck_ad_candidate_status", "active_directory_match_candidates", type_="check")
    op.drop_constraint("ck_ad_candidate_level", "active_directory_match_candidates", type_="check")
    op.drop_constraint("ck_ad_candidate_typed_target", "active_directory_match_candidates", type_="check")
    op.drop_index("ix_ad_candidates_candidate_department_id", table_name="active_directory_match_candidates")
    op.drop_index("ix_ad_candidates_candidate_discovery_id", table_name="active_directory_match_candidates")
    op.drop_constraint("fk_ad_candidate_department", "active_directory_match_candidates", type_="foreignkey")
    op.drop_constraint("fk_ad_candidate_discovery", "active_directory_match_candidates", type_="foreignkey")
    for column in ("target_version", "source_version", "candidate_role_id", "candidate_department_id", "candidate_discovery_id"):
        op.drop_column("active_directory_match_candidates", column)
    op.execute("UPDATE active_directory_match_candidates SET match_level = CASE match_level WHEN 'strong' THEN 'high' WHEN 'probable' THEN 'medium' WHEN 'weak' THEN 'low' ELSE match_level END")
    op.execute("UPDATE active_directory_match_candidates SET match_status = 'auto_matched' WHERE match_status = 'resolved'")
    op.create_unique_constraint("uq_ad_candidate_target", "active_directory_match_candidates", ["directory_object_id", "candidate_type", "candidate_user_id", "candidate_device_id"])
    op.create_check_constraint("ck_ad_candidate_typed_target", "active_directory_match_candidates", "(candidate_type = 'hiop_user' AND candidate_user_id IS NOT NULL AND candidate_device_id IS NULL) OR (candidate_type = 'hiop_device' AND candidate_device_id IS NOT NULL AND candidate_user_id IS NULL)")
    op.create_check_constraint("ck_ad_candidate_level", "active_directory_match_candidates", "match_level IN ('exact','high','medium','low','none')")
    op.create_check_constraint("ck_ad_candidate_status", "active_directory_match_candidates", "match_status IN ('pending','accepted','rejected','auto_matched')")
    op.create_check_constraint("ck_ad_candidate_action", "active_directory_match_candidates", "recommended_action IN ('link','create','enrich','review','ignore')")
