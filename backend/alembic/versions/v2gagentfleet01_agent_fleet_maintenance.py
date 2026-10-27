"""add managed endpoint telemetry, downloads, and maintenance rules

Revision ID: v2gagentfleet01
Revises: v2fagentact01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "v2gagentfleet01"
down_revision = "v2fagentact01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("local_agent_registrations", sa.Column("cpu_percent", sa.Float(), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("memory_total_bytes", sa.BigInteger(), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("memory_free_bytes", sa.BigInteger(), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("disk_free_bytes", sa.BigInteger(), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("ip_address", sa.String(64), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("operating_system", sa.String(255), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("logged_user", sa.String(255), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("last_update", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "agent_maintenance_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id", ondelete="CASCADE")),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("criteria", sa.Text(), nullable=False),
        sa.Column("schedule", sa.Text(), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_maintenance_rules_organization_id", "agent_maintenance_rules", ["organization_id"])
    op.create_index("ix_agent_maintenance_rules_property_id", "agent_maintenance_rules", ["property_id"])
    op.create_table(
        "agent_download_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("client_ip", sa.String(64), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_download_events_downloaded_at", "agent_download_events", ["downloaded_at"])
    op.create_table(
        "agent_metric_samples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("local_agent_registrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("properties.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uptime_seconds", sa.BigInteger()),
        sa.Column("cpu_percent", sa.Float()),
        sa.Column("memory_total_bytes", sa.BigInteger()),
        sa.Column("memory_free_bytes", sa.BigInteger()),
        sa.Column("disk_free_bytes", sa.BigInteger()),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agent_metric_samples_agent_id", "agent_metric_samples", ["agent_id"])
    op.create_index("ix_agent_metric_samples_organization_id", "agent_metric_samples", ["organization_id"])
    op.create_index("ix_agent_metric_samples_property_id", "agent_metric_samples", ["property_id"])
    op.create_index("ix_agent_metric_samples_recorded_at", "agent_metric_samples", ["recorded_at"])


def downgrade():
    op.drop_index("ix_agent_metric_samples_recorded_at", table_name="agent_metric_samples")
    op.drop_index("ix_agent_metric_samples_property_id", table_name="agent_metric_samples")
    op.drop_index("ix_agent_metric_samples_organization_id", table_name="agent_metric_samples")
    op.drop_index("ix_agent_metric_samples_agent_id", table_name="agent_metric_samples")
    op.drop_table("agent_metric_samples")
    op.drop_index("ix_agent_download_events_downloaded_at", table_name="agent_download_events")
    op.drop_table("agent_download_events")
    op.drop_index("ix_agent_maintenance_rules_property_id", table_name="agent_maintenance_rules")
    op.drop_index("ix_agent_maintenance_rules_organization_id", table_name="agent_maintenance_rules")
    op.drop_table("agent_maintenance_rules")
    for column in ("last_update", "logged_user", "operating_system", "ip_address", "disk_free_bytes", "memory_free_bytes", "memory_total_bytes", "cpu_percent"):
        op.drop_column("local_agent_registrations", column)
