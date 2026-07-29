"""seed safe automation actions

Revision ID: f3a4b5c6d7e9
Revises: f2a3b4c5d6e7
"""
from alembic import op
import sqlalchemy as sa

revision="f3a4b5c6d7e9";down_revision="f2a3b4c5d6e7";branch_labels=None;depends_on=None


def upgrade():
    table=sa.table("automation_actions",sa.column("action_key",sa.String),sa.column("name",sa.String),sa.column("description",sa.Text),sa.column("risk_level",sa.String),sa.column("property_scoped",sa.Boolean),sa.column("enabled",sa.Boolean),sa.column("approval_required",sa.Boolean))
    op.bulk_insert(table,[
        {"action_key":"noop","name":"No operation","description":"Validate workflow control flow without an external side effect.","risk_level":"low","property_scoped":True,"enabled":True,"approval_required":False},
        {"action_key":"record_event","name":"Record workflow event","description":"Record a bounded internal workflow execution event.","risk_level":"low","property_scoped":True,"enabled":True,"approval_required":False},
    ])


def downgrade():
    op.execute("DELETE FROM automation_actions WHERE action_key IN ('noop','record_event')")
