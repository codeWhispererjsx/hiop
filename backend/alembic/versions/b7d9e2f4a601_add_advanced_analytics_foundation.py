"""add advanced analytics foundation

Revision ID: b7d9e2f4a601
Revises: fa6d8e1c4b20
"""
from alembic import op

from app.models.analytics import (
    AnalyticsAggregate, AnalyticsAvailability, AnalyticsDataQualityRecord,
    AnalyticsMetricDefinition, AnalyticsRun, CapacityAssessment, CapacityPolicy,
    EntityHealthScore, HealthScoreConfiguration, ReliabilityMeasurement,
    SLADefinition, SLAMeasurement,
)

revision = "b7d9e2f4a601"
down_revision = "fa6d8e1c4b20"
branch_labels = None
depends_on = None

TABLES = (
    AnalyticsMetricDefinition.__table__,
    AnalyticsAggregate.__table__,
    AnalyticsAvailability.__table__,
    EntityHealthScore.__table__,
    HealthScoreConfiguration.__table__,
    CapacityPolicy.__table__,
    CapacityAssessment.__table__,
    SLADefinition.__table__,
    SLAMeasurement.__table__,
    ReliabilityMeasurement.__table__,
    AnalyticsRun.__table__,
    AnalyticsDataQualityRecord.__table__,
)


def upgrade():
    bind = op.get_bind()
    for table in TABLES:
        table.create(bind, checkfirst=False)


def downgrade():
    bind = op.get_bind()
    for table in reversed(TABLES):
        table.drop(bind, checkfirst=False)
