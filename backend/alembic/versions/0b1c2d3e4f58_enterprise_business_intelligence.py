"""Enterprise Reporting, Executive Dashboards and BI.

Revision ID: 0b1c2d3e4f58
Revises: e2f3a4b5c6d7
"""
from alembic import op
from app.models.business_intelligence import KPI,KPIDefinition,KPIValue,KPITarget,KPIThreshold,KPISnapshot,ExecutiveDashboard,DashboardWidget,DashboardCache,Report,ReportTemplate,ReportSection,ReportExecution,ScheduledReport,ReportRecipient
revision="0b1c2d3e4f58";down_revision="e2f3a4b5c6d7";branch_labels=None;depends_on=None
TABLES=[KPIDefinition,KPI,KPIValue,KPITarget,KPIThreshold,KPISnapshot,ExecutiveDashboard,DashboardWidget,DashboardCache,ReportTemplate,Report,ReportSection,ReportExecution,ScheduledReport,ReportRecipient]
def upgrade():
    bind=op.get_bind()
    for model in TABLES:model.__table__.create(bind,checkfirst=True)
def downgrade():
    bind=op.get_bind()
    for model in reversed(TABLES):model.__table__.drop(bind,checkfirst=True)
