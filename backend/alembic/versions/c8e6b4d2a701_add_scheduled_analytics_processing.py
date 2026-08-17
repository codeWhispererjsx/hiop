"""add scheduled analytics processing

Revision ID: c8e6b4d2a701
Revises: b7d9e2f4a601
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision = "c8e6b4d2a701"
down_revision = "b7d9e2f4a601"
branch_labels = None
depends_on = None


def upgrade():
    existing_run_columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("analytics_runs")
    }
    op.create_table(
        "analytics_schedule_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("aggregate_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("aggregate_interval_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("availability_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("availability_interval_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column("health_score_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("health_score_interval_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column("capacity_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("capacity_interval_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("sla_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("sla_interval_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("reliability_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("reliability_interval_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("data_quality_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("data_quality_interval_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("retention_cleanup_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("retention_cleanup_interval_hours", sa.Integer(), server_default="24", nullable=False),
        sa.Column("default_lookback_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("late_data_overlap_minutes", sa.Integer(), server_default="15", nullable=False),
        sa.Column("maximum_entities_per_run", sa.Integer(), server_default="500", nullable=False),
        sa.Column("maximum_run_duration_minutes", sa.Integer(), server_default="30", nullable=False),
        sa.Column("batch_size", sa.Integer(), server_default="100", nullable=False),
        sa.Column("jitter_seconds", sa.Integer(), server_default="30", nullable=False),
        sa.Column("stale_run_timeout_minutes", sa.Integer(), server_default="60", nullable=False),
        sa.Column("paused", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "analytics_checkpoints",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("metric_definition_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analytics_metric_definitions.id", ondelete="CASCADE")),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("bucket_size", sa.String(20), nullable=False),
        sa.Column("calculation_type", sa.String(30), nullable=False),
        sa.Column("completed_through", sa.DateTime(timezone=True)),
        sa.Column("last_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("analytics_runs.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("metric_definition_id", "entity_type", "entity_id", "bucket_size", "calculation_type", name="uq_analytics_checkpoint_scope"),
    )
    op.create_index("ix_analytics_checkpoint_updated", "analytics_checkpoints", ["updated_at"])
    op.create_table(
        "analytics_retention_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("record_type", sa.String(40), nullable=False),
        sa.Column("bucket_size", sa.String(20)),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("preserve_latest", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("preserve_breaches", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("preserve_sla_periods", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_by", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("record_type", "bucket_size", name="uq_analytics_retention_type_bucket"),
    )
    schedule = sa.table("analytics_schedule_configurations", sa.column("id", postgresql.UUID()), sa.column("enabled", sa.Boolean()))
    op.bulk_insert(schedule, [{"id": uuid.uuid4(), "enabled": False}])
    policies = sa.table(
        "analytics_retention_policies",
        sa.column("id", postgresql.UUID()), sa.column("record_type", sa.String()),
        sa.column("bucket_size", sa.String()), sa.column("retention_days", sa.Integer()),
    )
    op.bulk_insert(policies, [
        {"id": uuid.uuid4(), "record_type": "aggregate", "bucket_size": "5_minutes", "retention_days": 30},
        {"id": uuid.uuid4(), "record_type": "aggregate", "bucket_size": "15_minutes", "retention_days": 90},
        {"id": uuid.uuid4(), "record_type": "aggregate", "bucket_size": "1_hour", "retention_days": 730},
        {"id": uuid.uuid4(), "record_type": "data_quality", "bucket_size": None, "retention_days": 730},
        {"id": uuid.uuid4(), "record_type": "run", "bucket_size": None, "retention_days": 365},
    ])
    for name, kind, default in (
        ("job_id", sa.String(120), None), ("schedule_type", sa.String(30), None),
        ("bucket_sizes", postgresql.JSONB(), sa.text("'[]'::jsonb")),
        ("checkpoint_before", postgresql.JSONB(), sa.text("'{}'::jsonb")),
        ("checkpoint_after", postgresql.JSONB(), sa.text("'{}'::jsonb")),
        ("batches_total", sa.Integer(), "0"), ("batches_completed", sa.Integer(), "0"),
        ("records_created", sa.Integer(), "0"), ("records_updated", sa.Integer(), "0"),
        ("records_skipped", sa.Integer(), "0"), ("retry_count", sa.Integer(), "0"),
        ("stale_recovery_status", sa.String(30), None),
    ):
        if name not in existing_run_columns:
            op.add_column("analytics_runs", sa.Column(name, kind, server_default=default, nullable=default is not None))


def downgrade():
    for name in reversed(("job_id", "schedule_type", "bucket_sizes", "checkpoint_before", "checkpoint_after", "batches_total", "batches_completed", "records_created", "records_updated", "records_skipped", "retry_count", "stale_recovery_status")):
        op.drop_column("analytics_runs", name)
    op.drop_table("analytics_retention_policies")
    op.drop_index("ix_analytics_checkpoint_updated", table_name="analytics_checkpoints")
    op.drop_table("analytics_checkpoints")
    op.drop_table("analytics_schedule_configurations")
