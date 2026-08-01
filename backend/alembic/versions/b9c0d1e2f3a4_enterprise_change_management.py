"""enterprise change, release, CAB, risk, maintenance, and execution management

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
"""
from alembic import op

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None

TABLES = (
    "change_types", "change_categories", "change_priorities", "change_risks", "change_impacts",
    "change_requests", "change_approvals", "change_tasks", "change_comments", "change_attachments", "change_revisions",
    "cab_meetings", "cab_members", "cab_agenda_items", "cab_attendance", "cab_votes", "cab_decisions",
    "risk_assessments", "risk_factors", "mitigation_plans", "change_business_impacts", "change_technical_impacts",
    "maintenance_calendars", "maintenance_windows", "maintenance_approvals", "maintenance_conflicts",
    "change_executions", "change_execution_tasks", "change_execution_evidence", "change_execution_logs", "rollback_executions",
    "releases", "release_packages", "release_versions", "release_deployments", "release_artifacts",
    "change_communications", "change_relationships",
)

CHANGE_TYPES = (
    ("Standard Change", "standard", "standard", False), ("Normal Change", "normal", "technical_and_cab", True),
    ("Emergency Change", "emergency", "emergency_cab", True), ("Major Change", "major", "technical_and_cab", True),
    ("Routine Maintenance", "routine_maintenance", "technical", True), ("Infrastructure Upgrade", "infrastructure_upgrade", "technical_and_cab", True),
    ("Software Deployment", "software_deployment", "technical_and_cab", True), ("Network Change", "network", "technical_and_cab", True),
    ("Security Change", "security", "technical_and_cab", True), ("Database Change", "database", "technical_and_cab", True),
    ("Cloud Change", "cloud", "technical_and_cab", True), ("Hospitality Service Change", "hospitality_service", "technical_and_cab", True),
)


def upgrade():
    from app.models import change_management  # noqa: F401
    from app.models import hospitality_operations  # noqa: F401
    from app.db.database import Base
    bind = op.get_bind()
    for table_name in TABLES: Base.metadata.tables[table_name].create(bind, checkfirst=True)
    types = Base.metadata.tables["change_types"]
    for name, code, policy, rollback in CHANGE_TYPES:
        bind.execute(types.insert().values(name=name, code=code, approval_policy=policy, risk_template="{}", default_tasks="[]", rollback_required=rollback, enabled=True))
    categories = Base.metadata.tables["change_categories"]
    for name, code in (("Infrastructure", "infrastructure"), ("Application", "application"), ("Network", "network"), ("Security", "security"), ("Database", "database"), ("Hospitality Service", "hospitality_service")):
        bind.execute(categories.insert().values(name=name, code=code, enabled=True))


def downgrade():
    for table_name in reversed(TABLES): op.drop_table(table_name)
