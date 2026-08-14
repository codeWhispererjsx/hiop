"""V4G practical change management

Revision ID: v4g0a1b2c3d4
Revises: v4f0a1b2c3d4
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v4g0a1b2c3d4"
down_revision = "v4f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("change_requests", sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("change_requests", sa.Column("change_type", sa.String(20), server_default="normal", nullable=False))
    op.add_column("change_requests", sa.Column("risk_explanation", sa.Text()))
    op.add_column("change_requests", sa.Column("approver_id", sa.String()))
    op.add_column("change_requests", sa.Column("approved_at", sa.DateTime(timezone=True)))
    op.add_column("change_requests", sa.Column("actual_start", sa.DateTime(timezone=True)))
    op.add_column("change_requests", sa.Column("actual_end", sa.DateTime(timezone=True)))
    op.add_column("change_requests", sa.Column("outcome", sa.String(30)))
    op.add_column("change_requests", sa.Column("closure_notes", sa.Text()))
    op.add_column("change_requests", sa.Column("closed_by", sa.String()))
    op.add_column("change_requests", sa.Column("rollback_time", sa.DateTime(timezone=True)))
    op.add_column("change_requests", sa.Column("rollback_owner_id", sa.String()))
    op.add_column("change_requests", sa.Column("rollback_reason", sa.Text()))
    op.add_column("change_requests", sa.Column("rollback_notes", sa.Text()))
    op.create_foreign_key("fk_change_org", "change_requests", "organizations", ["organization_id"], ["id"])
    for column, name in (("approver_id", "fk_change_approver"), ("closed_by", "fk_change_closed_by"), ("rollback_owner_id", "fk_change_rollback_owner")):
        op.create_foreign_key(name, "change_requests", "users", [column], ["id"])
    op.create_index("ix_change_requests_organization_id", "change_requests", ["organization_id"])
    op.execute("UPDATE change_requests c SET organization_id=p.organization_id FROM properties p WHERE c.property_id=p.id AND c.organization_id IS NULL")
    op.execute("CREATE SEQUENCE IF NOT EXISTS v4g_change_number_seq START 1")
    op.create_table("change_timeline_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("change_request_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("change_requests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False), sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(), sa.ForeignKey("users.id")), sa.Column("actor_name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_change_timeline_change", "change_timeline_events", ["change_request_id"])
    op.create_index("ix_change_timeline_org", "change_timeline_events", ["organization_id"])


def downgrade():
    op.drop_table("change_timeline_events")
    op.execute("DROP SEQUENCE IF EXISTS v4g_change_number_seq")
    op.drop_index("ix_change_requests_organization_id", table_name="change_requests")
    for name in ("fk_change_rollback_owner", "fk_change_closed_by", "fk_change_approver", "fk_change_org"):
        op.drop_constraint(name, "change_requests", type_="foreignkey")
    for column in ("rollback_notes", "rollback_reason", "rollback_owner_id", "rollback_time", "closed_by", "closure_notes", "outcome", "actual_end", "actual_start", "approved_at", "approver_id", "risk_explanation", "change_type", "organization_id"):
        op.drop_column("change_requests", column)
