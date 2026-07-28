"""add analytics forecasts

Revision ID: d9f7c5e3b812
Revises: c8e6b4d2a701
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d9f7c5e3b812"
down_revision = "c8e6b4d2a701"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "analytics_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_key", sa.String(120), nullable=False),
        sa.Column("forecast_method", sa.String(30), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("forecast_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prediction_points", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("projected_value", sa.Float(), nullable=False),
        sa.Column("lower_bound", sa.Float(), nullable=False),
        sa.Column("upper_bound", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("growth_rate", sa.Float(), nullable=False),
        sa.Column("trend_direction", sa.String(20), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(20), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("data_quality", sa.String(20), nullable=False),
        sa.Column("assumptions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("calculation_version", sa.String(20), server_default="1.0", nullable=False),
        sa.Column("evaluated_at", sa.DateTime(timezone=True)),
        sa.Column("actual_value", sa.Float()),
        sa.Column("forecast_error", sa.Float()),
        sa.Column("accuracy_percent", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_analytics_forecast_entity_metric", "analytics_forecasts", ["entity_type", "entity_id", "metric_key"])
    op.create_index("ix_analytics_forecast_created", "analytics_forecasts", ["created_at"])


def downgrade():
    op.drop_index("ix_analytics_forecast_created", table_name="analytics_forecasts")
    op.drop_index("ix_analytics_forecast_entity_metric", table_name="analytics_forecasts")
    op.drop_table("analytics_forecasts")
