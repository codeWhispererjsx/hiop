"""complete automation orchestration persistence

Revision ID: f5c6d7e8f9a0
Revises: f4b5c6d7e8f9
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="f5c6d7e8f9a0";down_revision="f4b5c6d7e8f9";branch_labels=None;depends_on=None
u=postgresql.UUID(as_uuid=True)

def upgrade():
    for column in [
        sa.Column("correlation_threshold",sa.Integer(),server_default="1",nullable=False),
        sa.Column("maximum_correlation_members",sa.Integer(),server_default="100",nullable=False),
        sa.Column("recovery_event_type",sa.String(80)),
    ]:op.add_column("automation_trigger_subscriptions",column)
    for column in [
        sa.Column("day_of_week",sa.Integer()),sa.Column("day_of_month",sa.Integer()),
        sa.Column("preferred_time",sa.String(5)),sa.Column("start_at",sa.DateTime(timezone=True)),
        sa.Column("end_at",sa.DateTime(timezone=True)),sa.Column("jitter_seconds",sa.Integer(),server_default="0",nullable=False),
        sa.Column("blackout_behavior",sa.String(30),server_default="suppress",nullable=False),
    ]:op.add_column("automation_workflow_schedules",column)
    op.create_table("automation_event_outbox",
        sa.Column("id",u,primary_key=True),sa.Column("event_id",u,nullable=False,unique=True),
        sa.Column("event_type",sa.String(80),nullable=False),sa.Column("property_id",u,sa.ForeignKey("properties.id")),
        sa.Column("payload",sa.Text(),nullable=False),sa.Column("status",sa.String(20),server_default="pending",nullable=False),
        sa.Column("attempts",sa.Integer(),server_default="0",nullable=False),sa.Column("next_attempt_at",sa.DateTime(timezone=True)),
        sa.Column("published_at",sa.DateTime(timezone=True)),sa.Column("error_summary",sa.String(500)),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_automation_outbox_status_next","automation_event_outbox",["status","next_attempt_at"])
    op.create_index("ix_automation_outbox_property","automation_event_outbox",["property_id"])
    op.create_table("automation_trigger_correlation_groups",
        sa.Column("id",u,primary_key=True),sa.Column("subscription_id",u,sa.ForeignKey("automation_trigger_subscriptions.id",ondelete="CASCADE"),nullable=False),
        sa.Column("property_id",u,sa.ForeignKey("properties.id")),sa.Column("correlation_key",sa.String(160),nullable=False),
        sa.Column("status",sa.String(20),server_default="collecting",nullable=False),sa.Column("first_event_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("last_event_at",sa.DateTime(timezone=True),nullable=False),sa.Column("event_count",sa.Integer(),server_default="0",nullable=False),
        sa.Column("member_event_ids",sa.Text(),server_default="[]",nullable=False),sa.Column("threshold_reached",sa.Boolean(),server_default=sa.text("false"),nullable=False),
        sa.Column("workflow_run_id",u,sa.ForeignKey("automation_workflow_runs.id")),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_automation_correlation_expiry","automation_trigger_correlation_groups",["status","expires_at"])
    op.create_index("ix_automation_correlation_key_status","automation_trigger_correlation_groups",["subscription_id","correlation_key","status"])
    op.create_table("automation_trigger_revisions",
        sa.Column("id",u,primary_key=True),sa.Column("subscription_id",u,sa.ForeignKey("automation_trigger_subscriptions.id",ondelete="CASCADE"),nullable=False),
        sa.Column("revision_number",sa.Integer(),nullable=False),sa.Column("configuration_snapshot",sa.Text(),nullable=False),
        sa.Column("checksum",sa.String(64),nullable=False),sa.Column("status",sa.String(20),server_default="draft",nullable=False),
        sa.Column("created_by",sa.String()),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.UniqueConstraint("subscription_id","revision_number",name="uq_automation_trigger_revision"))
    op.create_index("ix_automation_trigger_revision_subscription","automation_trigger_revisions",["subscription_id"])

def downgrade():
    op.drop_index("ix_automation_trigger_revision_subscription",table_name="automation_trigger_revisions");op.drop_table("automation_trigger_revisions")
    op.drop_index("ix_automation_correlation_key_status",table_name="automation_trigger_correlation_groups");op.drop_index("ix_automation_correlation_expiry",table_name="automation_trigger_correlation_groups");op.drop_table("automation_trigger_correlation_groups")
    op.drop_index("ix_automation_outbox_property",table_name="automation_event_outbox");op.drop_index("ix_automation_outbox_status_next",table_name="automation_event_outbox");op.drop_table("automation_event_outbox")
    for name in ["blackout_behavior","jitter_seconds","end_at","start_at","preferred_time","day_of_month","day_of_week"]:op.drop_column("automation_workflow_schedules",name)
    for name in ["recovery_event_type","maximum_correlation_members","correlation_threshold"]:op.drop_column("automation_trigger_subscriptions",name)
