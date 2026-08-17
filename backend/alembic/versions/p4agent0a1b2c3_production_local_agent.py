"""production local hotel agent

Revision ID: p4agent0a1b2c3
Revises: billing0a1b2c3d
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision="p4agent0a1b2c3";down_revision="billing0a1b2c3d";branch_labels=None;depends_on=None

def upgrade():
    for name,column in [
        ("hostname",sa.Column("hostname",sa.String(255))),
        ("credential_hash",sa.Column("credential_hash",sa.String(64))),
        ("credential_expires_at",sa.Column("credential_expires_at",sa.DateTime(timezone=True))),
        ("last_discovery",sa.Column("last_discovery",sa.DateTime(timezone=True))),
        ("last_monitoring",sa.Column("last_monitoring",sa.DateTime(timezone=True))),
        ("uptime_seconds",sa.Column("uptime_seconds",sa.BigInteger())),
        ("pending_queue",sa.Column("pending_queue",sa.Integer(),server_default="0",nullable=False)),
        ("queue_capacity",sa.Column("queue_capacity",sa.Integer(),server_default="10000",nullable=False)),
        ("revoked_at",sa.Column("revoked_at",sa.DateTime(timezone=True))),
        ("retired_at",sa.Column("retired_at",sa.DateTime(timezone=True))),
    ]:op.add_column("local_agent_registrations",column)
    op.create_unique_constraint("uq_local_agent_credential_hash","local_agent_registrations",["credential_hash"])
    op.drop_constraint("ck_local_agent_status","local_agent_registrations",type_="check")
    op.create_check_constraint("ck_local_agent_status","local_agent_registrations","status IN ('pending','online','offline','stale','revoked','retired','unknown')")
    u=postgresql.UUID(as_uuid=True)
    op.create_table("agent_enrollments",
        sa.Column("id",u,primary_key=True),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False),sa.Column("property_id",u,sa.ForeignKey("properties.id",ondelete="CASCADE"),nullable=False),sa.Column("name",sa.String(160),nullable=False),sa.Column("token_hash",sa.String(64),nullable=False,unique=True),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.Column("used_at",sa.DateTime(timezone=True)),sa.Column("revoked_at",sa.DateTime(timezone=True)),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("created_by",sa.String(),sa.ForeignKey("users.id"),nullable=False))
    op.create_index("ix_agent_enrollments_organization_id","agent_enrollments",["organization_id"]);op.create_index("ix_agent_enrollments_property_id","agent_enrollments",["property_id"])
    op.create_table("agent_jobs",
        sa.Column("id",u,primary_key=True),sa.Column("agent_id",u,sa.ForeignKey("local_agent_registrations.id",ondelete="CASCADE"),nullable=False),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False),sa.Column("property_id",u,sa.ForeignKey("properties.id",ondelete="CASCADE"),nullable=False),sa.Column("job_type",sa.String(40),nullable=False),sa.Column("payload",sa.Text(),server_default="{}",nullable=False),sa.Column("status",sa.String(20),server_default="queued",nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("available_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("started_at",sa.DateTime(timezone=True)),sa.Column("completed_at",sa.DateTime(timezone=True)),sa.Column("timeout_seconds",sa.Integer(),server_default="120",nullable=False),sa.Column("error",sa.String(1000)),sa.Column("created_by",sa.String(),sa.ForeignKey("users.id")))
    for col in ("agent_id","organization_id","property_id","status"):op.create_index(f"ix_agent_jobs_{col}","agent_jobs",[col])
    op.create_table("agent_observations",
        sa.Column("id",u,primary_key=True),sa.Column("observation_id",sa.String(80),nullable=False),sa.Column("agent_id",u,sa.ForeignKey("local_agent_registrations.id",ondelete="CASCADE"),nullable=False),sa.Column("organization_id",u,sa.ForeignKey("organizations.id",ondelete="CASCADE"),nullable=False),sa.Column("property_id",u,sa.ForeignKey("properties.id",ondelete="CASCADE"),nullable=False),sa.Column("source",sa.String(40),nullable=False),sa.Column("schema_version",sa.Integer(),server_default="1",nullable=False),sa.Column("observed_at",sa.DateTime(timezone=True),nullable=False),sa.Column("payload",sa.Text(),nullable=False),sa.Column("accepted_at",sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),sa.Column("processed",sa.Boolean(),server_default=sa.false(),nullable=False),sa.UniqueConstraint("agent_id","observation_id",name="uq_agent_observation"))
    for col in ("agent_id","organization_id","property_id"):op.create_index(f"ix_agent_observations_{col}","agent_observations",[col])

def downgrade():
    op.drop_table("agent_observations");op.drop_table("agent_jobs");op.drop_table("agent_enrollments")
    op.drop_constraint("ck_local_agent_status","local_agent_registrations",type_="check");op.create_check_constraint("ck_local_agent_status","local_agent_registrations","status IN ('online','offline','unknown')")
    op.drop_constraint("uq_local_agent_credential_hash","local_agent_registrations",type_="unique")
    for name in ("retired_at","revoked_at","queue_capacity","pending_queue","uptime_seconds","last_monitoring","last_discovery","credential_expires_at","credential_hash","hostname"):op.drop_column("local_agent_registrations",name)
