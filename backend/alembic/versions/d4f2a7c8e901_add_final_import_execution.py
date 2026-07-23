"""Add transactional final import execution and rollback persistence.

Revision ID: d4f2a7c8e901
Revises: 91b7d3e5a204
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d4f2a7c8e901"
down_revision = "91b7d3e5a204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("import_session_status", "import_sessions", type_="check")
    op.alter_column("import_sessions", "status", type_=sa.String(20), existing_type=sa.String(10), existing_nullable=False)
    op.create_check_constraint(
        "import_session_status",
        "import_sessions",
        "status IN ('uploaded','validating','processing','review_required','ready','importing','completed','partial','failed','cancelled','rolled_back')",
    )
    op.add_column("import_sessions", sa.Column("execution_summary", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("import_sessions", sa.Column("plan_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("import_sessions", sa.Column("plan_locked_at", sa.DateTime(timezone=True)))
    op.add_column("import_sessions", sa.Column("finalized_by", sa.String()))
    op.add_column("import_sessions", sa.Column("finalization_started_at", sa.DateTime(timezone=True)))
    op.add_column("import_sessions", sa.Column("finalization_completed_at", sa.DateTime(timezone=True)))
    op.add_column("import_sessions", sa.Column("rollback_by", sa.String()))
    op.add_column("import_sessions", sa.Column("rollback_at", sa.DateTime(timezone=True)))
    op.add_column("import_sessions", sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False))
    op.create_foreign_key("fk_import_sessions_finalized_by", "import_sessions", "users", ["finalized_by"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_import_sessions_rollback_by", "import_sessions", "users", ["rollback_by"], ["id"], ondelete="SET NULL")
    op.add_column("imported_devices", sa.Column("device_type", sa.String(80)))
    op.add_column("imported_devices", sa.Column("final_disposition", sa.String(32)))
    op.add_column("imported_devices", sa.Column("approved_changes", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.create_table(
        "import_execution_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("import_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("import_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("imported_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("imported_devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("target_device_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("devices.id", ondelete="SET NULL")),
        sa.Column("target_discovery_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("discovered_devices.id", ondelete="SET NULL")),
        sa.Column("plan", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("before_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("after_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column("safe_error_message", sa.String(500)),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('pending','running','completed','failed','skipped','rolled_back','rollback_failed')", name="import_execution_status"),
    )
    op.create_index("uq_import_execution_results_row", "import_execution_results", ["import_session_id", "imported_device_id"], unique=True)
    op.create_index("ix_import_execution_results_status", "import_execution_results", ["status"])
    op.create_index("ix_import_execution_results_target", "import_execution_results", ["target_device_id"])


def downgrade() -> None:
    op.drop_table("import_execution_results")
    op.drop_column("imported_devices", "approved_changes")
    op.drop_column("imported_devices", "final_disposition")
    op.drop_column("imported_devices", "device_type")
    op.drop_constraint("fk_import_sessions_rollback_by", "import_sessions", type_="foreignkey")
    op.drop_constraint("fk_import_sessions_finalized_by", "import_sessions", type_="foreignkey")
    for column in (
        "retry_count",
        "rollback_at",
        "rollback_by",
        "finalization_completed_at",
        "finalization_started_at",
        "finalized_by",
        "plan_locked_at",
        "plan_version",
        "execution_summary",
    ):
        op.drop_column("import_sessions", column)
    op.drop_constraint("import_session_status", "import_sessions", type_="check")
    op.execute("UPDATE import_sessions SET status='partial' WHERE status IN ('review_required','ready','importing','cancelled','rolled_back')")
    op.alter_column("import_sessions", "status", type_=sa.String(10), existing_type=sa.String(20), existing_nullable=False)
    op.create_check_constraint("import_session_status", "import_sessions", "status IN ('uploaded','validating','processing','completed','partial','failed')")
