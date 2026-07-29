"""expand automation orchestration

Revision ID: f4b5c6d7e8f9
Revises: f3a4b5c6d7e9
"""
from alembic import op
import sqlalchemy as sa

revision="f4b5c6d7e8f9";down_revision="f3a4b5c6d7e9";branch_labels=None;depends_on=None

def upgrade():
    for name,column in [
        ("event_version",sa.Column("event_version",sa.Integer(),server_default="1")),
        ("source_module",sa.Column("source_module",sa.String(50))),("severity",sa.Column("severity",sa.String(20))),
        ("status",sa.Column("status",sa.String(30))),("correlation_key",sa.Column("correlation_key",sa.String(160))),
        ("processed_at",sa.Column("processed_at",sa.DateTime(timezone=True))),("expires_at",sa.Column("expires_at",sa.DateTime(timezone=True)))]:
        op.add_column("automation_event_records",column)
    op.create_index("ix_automation_event_correlation","automation_event_records",["correlation_key"])
    for column in [
        sa.Column("filter_definition",sa.Text()),sa.Column("condition_definition",sa.Text()),sa.Column("input_mapping",sa.Text()),
        sa.Column("correlation_window_seconds",sa.Integer(),server_default="300"),sa.Column("maximum_runs_per_window",sa.Integer(),server_default="5"),
        sa.Column("run_window_seconds",sa.Integer(),server_default="3600"),sa.Column("delay_seconds",sa.Integer(),server_default="0"),
        sa.Column("approval_mode",sa.String(30),server_default="use_workflow_policy"),sa.Column("maintenance_behavior",sa.String(30),server_default="suppress"),
        sa.Column("blackout_behavior",sa.String(30),server_default="suppress"),sa.Column("blackout_start",sa.DateTime(timezone=True)),
        sa.Column("blackout_end",sa.DateTime(timezone=True)),sa.Column("created_by",sa.String())]:op.add_column("automation_trigger_subscriptions",column)
    for column in [
        sa.Column("approval_mode",sa.String(30),server_default="use_workflow_policy"),sa.Column("maintenance_behavior",sa.String(30),server_default="suppress"),
        sa.Column("blackout_start",sa.DateTime(timezone=True)),sa.Column("blackout_end",sa.DateTime(timezone=True)),
        sa.Column("last_run_at",sa.DateTime(timezone=True)),sa.Column("last_run_status",sa.String(30))]:op.add_column("automation_workflow_schedules",column)

def downgrade():
    for name in ["last_run_status","last_run_at","blackout_end","blackout_start","maintenance_behavior","approval_mode"]:op.drop_column("automation_workflow_schedules",name)
    for name in ["created_by","blackout_end","blackout_start","blackout_behavior","maintenance_behavior","approval_mode","delay_seconds","run_window_seconds","maximum_runs_per_window","correlation_window_seconds","input_mapping","condition_definition","filter_definition"]:op.drop_column("automation_trigger_subscriptions",name)
    op.drop_index("ix_automation_event_correlation",table_name="automation_event_records")
    for name in ["expires_at","processed_at","correlation_key","status","severity","source_module","event_version"]:op.drop_column("automation_event_records",name)
