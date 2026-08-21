"""system health and observability

Revision ID: p5health0a1b2c3
Revises: p4agent0a1b2c3
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="p5health0a1b2c3";down_revision="p4agent0a1b2c3";branch_labels=None;depends_on=None

def upgrade():
    u=postgresql.UUID(as_uuid=True)
    op.create_table("system_health_snapshots",
        sa.Column("id",u,primary_key=True),
        sa.Column("component",sa.String(40),nullable=False),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("last_success",sa.DateTime(timezone=True)),
        sa.Column("last_failure",sa.DateTime(timezone=True)),
        sa.Column("last_check",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("details",sa.Text()),
        sa.Column("organization_id",u,sa.ForeignKey("organizations.id"),index=True),
        sa.Column("property_id",u,sa.ForeignKey("properties.id"),index=True),
        sa.UniqueConstraint("component","organization_id","property_id",name="uq_health_component_org_prop"))
    op.create_index("ix_system_health_snapshots_component","system_health_snapshots",["component"])
    
    op.create_table("health_events",
        sa.Column("id",u,primary_key=True),
        sa.Column("component",sa.String(40),nullable=False),
        sa.Column("previous_status",sa.String(20)),
        sa.Column("new_status",sa.String(20),nullable=False),
        sa.Column("reason",sa.String(500)),
        sa.Column("organization_id",u,sa.ForeignKey("organizations.id"),index=True),
        sa.Column("property_id",u,sa.ForeignKey("properties.id"),index=True),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False))
    op.create_index("ix_health_events_component","health_events",["component"])
    op.create_index("ix_health_events_created","health_events",["created_at"])
    
    op.create_table("job_executions",
        sa.Column("id",u,primary_key=True),
        sa.Column("job_id",sa.String(100),nullable=False),
        sa.Column("job_type",sa.String(40),nullable=False),
        sa.Column("organization_id",u,sa.ForeignKey("organizations.id"),index=True),
        sa.Column("property_id",u,sa.ForeignKey("properties.id"),index=True),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("started_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("completed_at",sa.DateTime(timezone=True)),
        sa.Column("duration_seconds",sa.Integer()),
        sa.Column("error",sa.String(1000)),
        sa.Column("result_summary",sa.Text()),
        sa.Column("correlation_id",sa.String(64)))
    op.create_index("ix_job_executions_job_id","job_executions",["job_id"])
    op.create_index("ix_job_executions_started","job_executions",["started_at"])
    op.create_index("ix_job_executions_status","job_executions",["status"])
    
    op.create_table("notification_deliveries",
        sa.Column("id",u,primary_key=True),
        sa.Column("notification_type",sa.String(40),nullable=False),
        sa.Column("recipient",sa.String(255),nullable=False),
        sa.Column("status",sa.String(20),nullable=False),
        sa.Column("attempted_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.Column("delivered_at",sa.DateTime(timezone=True)),
        sa.Column("retry_count",sa.Integer(),server_default="0",nullable=False),
        sa.Column("error",sa.String(500)),
        sa.Column("organization_id",u,sa.ForeignKey("organizations.id"),index=True))
    op.create_index("ix_notification_deliveries_status","notification_deliveries",["status"])
    op.create_index("ix_notification_deliveries_attempted","notification_deliveries",["attempted_at"])

def downgrade():
    op.drop_table("notification_deliveries")
    op.drop_table("job_executions")
    op.drop_table("health_events")
    op.drop_table("system_health_snapshots")
