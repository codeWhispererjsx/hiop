"""Add local agent health telemetry and power event auditing."""

from alembic import op
import sqlalchemy as sa

revision = "phase2power001"
down_revision = "naming0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("local_agent_registrations", sa.Column("fast_startup_enabled", sa.Boolean(), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("lid_close_action", sa.String(length=80), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("battery_health_percent", sa.Float(), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("pending_windows_updates", sa.Integer(), nullable=True))
    op.add_column("local_agent_registrations", sa.Column("last_shutdown_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "agent_power_events",
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_id", sa.String(length=80), nullable=False),
        sa.Column("agent_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("organization_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("property_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("reason", sa.String(length=250), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["local_agent_registrations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_power_events_agent_id", "agent_power_events", ["agent_id"])
    op.create_index("ix_agent_power_events_organization_id", "agent_power_events", ["organization_id"])
    op.create_index("ix_agent_power_events_property_id", "agent_power_events", ["property_id"])
    op.create_index("ix_agent_power_events_recorded_at", "agent_power_events", ["recorded_at"])
    op.create_index("uq_agent_power_event", "agent_power_events", ["agent_id", "event_id"], unique=True)


def downgrade():
    op.drop_index("uq_agent_power_event", table_name="agent_power_events")
    op.drop_index("ix_agent_power_events_recorded_at", table_name="agent_power_events")
    op.drop_index("ix_agent_power_events_property_id", table_name="agent_power_events")
    op.drop_index("ix_agent_power_events_organization_id", table_name="agent_power_events")
    op.drop_index("ix_agent_power_events_agent_id", table_name="agent_power_events")
    op.drop_table("agent_power_events")
    op.drop_column("local_agent_registrations", "last_shutdown_at")
    op.drop_column("local_agent_registrations", "pending_windows_updates")
    op.drop_column("local_agent_registrations", "battery_health_percent")
    op.drop_column("local_agent_registrations", "lid_close_action")
    op.drop_column("local_agent_registrations", "fast_startup_enabled")
