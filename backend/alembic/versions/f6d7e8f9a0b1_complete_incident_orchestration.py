"""complete operational playbooks and incident orchestration

Revision ID: f6d7e8f9a0b1
Revises: f5c6d7e8f9a0
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f6d7e8f9a0b1"
down_revision = "f5c6d7e8f9a0"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def _add(table, *columns):
    for column in columns:
        op.add_column(table, column)


def upgrade():
    _add(
        "operational_incidents",
        sa.Column("organization_id", UUID, sa.ForeignKey("organizations.id")),
        sa.Column("source_type", sa.String(40)),
        sa.Column("source_reference_type", sa.String(60)),
        sa.Column("source_reference_id", UUID),
        sa.Column("technology_service_id", UUID),
        sa.Column("device_id", UUID, sa.ForeignKey("devices.id")),
        sa.Column("building_id", UUID, sa.ForeignKey("buildings.id")),
        sa.Column("floor_id", UUID, sa.ForeignKey("floors.id")),
        sa.Column("zone_id", UUID, sa.ForeignKey("zones.id")),
        sa.Column("department_id", UUID, sa.ForeignKey("departments.id")),
        sa.Column("security_impact_level", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("life_safety_impact_level", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("owner_user_id", sa.String(), sa.ForeignKey("users.id")),
        sa.Column("playbook_id", UUID),
        sa.Column("playbook_version_id", UUID),
        sa.Column("workflow_run_id", UUID),
        sa.Column("linked_ticket_id", UUID),
        sa.Column("duplicate_of_id", UUID, sa.ForeignKey("operational_incidents.id")),
        sa.Column("correlation_key", sa.String(160)),
        sa.Column("closure_summary", sa.Text()),
        sa.Column("closure_reason", sa.Text()),
        sa.Column("recovery_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("data_quality", sa.String(20), server_default="unknown", nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("contained_at", sa.DateTime(timezone=True)),
        sa.Column("mitigated_at", sa.DateTime(timezone=True)),
        sa.Column("recovered_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("last_communication_at", sa.DateTime(timezone=True)),
        sa.Column("updated_by", sa.String()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_operational_incidents_incident_type", "operational_incidents", ["incident_type"])
    op.create_index("ix_operational_incidents_priority", "operational_incidents", ["priority"])
    op.create_index("ix_operational_incidents_correlation_key", "operational_incidents", ["correlation_key"])
    op.create_index("ix_incident_property_status_created", "operational_incidents", ["property_id", "status", "created_at"])
    op.create_check_constraint("ck_incident_not_self_duplicate", "operational_incidents", "duplicate_of_id IS NULL OR duplicate_of_id <> id")

    _add(
        "operational_incident_sources",
        sa.Column("source_entity_type", sa.String(60)),
        sa.Column("source_status", sa.String(30)),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("linked_by", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_operational_incident_sources_source_entity_id", "operational_incident_sources", ["source_entity_id"])

    _add(
        "incident_participants",
        sa.Column("responsibility", sa.Text()),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True)),
        sa.Column("assigned_by", sa.String()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_active_incident_participant_role", "incident_participants", ["incident_id", "user_id", "participant_role"])

    _add(
        "incident_tasks",
        sa.Column("playbook_run_id", UUID),
        sa.Column("step_run_id", UUID),
        sa.Column("description", sa.Text()),
        sa.Column("task_type", sa.String(30), server_default="investigation", nullable=False),
        sa.Column("priority", sa.String(4), server_default="P3", nullable=False),
        sa.Column("assigned_role", sa.String(40)),
        sa.Column("created_by", sa.String()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by", sa.String()),
        sa.Column("verification_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verified_by", sa.String()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_incident_tasks_due_at", "incident_tasks", ["due_at"])

    _add(
        "incident_timeline_entries",
        sa.Column("source_type", sa.String(40)),
        sa.Column("source_id", UUID),
        sa.Column("severity", sa.String(20)),
        sa.Column("property_id", UUID, sa.ForeignKey("properties.id")),
        sa.Column("safe_metadata", sa.Text(), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_incident_timeline_entries_entry_type", "incident_timeline_entries", ["entry_type"])
    op.create_index("ix_incident_timeline_incident_time", "incident_timeline_entries", ["incident_id", "occurred_at"])

    # New tables are created from the application metadata so migration columns remain
    # exactly aligned with the ORM. Existing tables above are altered explicitly.
    from app.models.automation import (
        AutomationWorkflowVersion, AutomationAction, AutomationWorkflowRun,
    )
    from app.models.incidents import (
        OperationalPlaybook, OperationalPlaybookVersion, OperationalPlaybookStep,
        IncidentPlaybookRun, IncidentPlaybookStepRun, IncidentChecklistItem,
        IncidentEvidence, IncidentDecision, IncidentCommunicationTemplate,
        IncidentCommunication, IncidentEscalationRule, IncidentEscalation,
        IncidentResponseTarget, IncidentImpactAssessment,
        IncidentRemediationRecommendation, IncidentCauseAssessment,
        PostIncidentReview, IncidentFollowUpAction,
    )
    bind = op.get_bind()
    models = (
        OperationalPlaybook, OperationalPlaybookVersion, OperationalPlaybookStep,
        IncidentPlaybookRun, IncidentPlaybookStepRun, IncidentChecklistItem,
        IncidentEvidence, IncidentDecision, IncidentCommunicationTemplate,
        IncidentCommunication, IncidentEscalationRule, IncidentEscalation,
        IncidentResponseTarget, IncidentImpactAssessment,
        IncidentRemediationRecommendation, IncidentCauseAssessment,
        PostIncidentReview, IncidentFollowUpAction,
    )
    for model in models:
        model.__table__.create(bind, checkfirst=True)
    op.create_foreign_key("fk_incident_tasks_playbook_run", "incident_tasks", "incident_playbook_runs", ["playbook_run_id"], ["id"])
    op.create_foreign_key("fk_incident_tasks_step_run", "incident_tasks", "incident_playbook_step_runs", ["step_run_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_incident_tasks_step_run", "incident_tasks", type_="foreignkey")
    op.drop_constraint("fk_incident_tasks_playbook_run", "incident_tasks", type_="foreignkey")
    for table in (
        "incident_follow_up_actions", "post_incident_reviews", "incident_cause_assessments",
        "incident_remediation_recommendations", "incident_impact_assessments",
        "incident_response_targets", "incident_escalations", "incident_escalation_rules",
        "incident_communications", "incident_communication_templates", "incident_decisions",
        "incident_evidence", "incident_checklist_items", "incident_playbook_step_runs",
        "incident_playbook_runs", "operational_playbook_steps",
        "operational_playbook_versions", "operational_playbooks",
    ):
        op.drop_table(table)

    op.drop_index("ix_incident_timeline_incident_time", table_name="incident_timeline_entries")
    op.drop_index("ix_incident_timeline_entries_entry_type", table_name="incident_timeline_entries")
    for column in ("created_at", "safe_metadata", "property_id", "severity", "source_id", "source_type"):
        op.drop_column("incident_timeline_entries", column)
    op.drop_index("ix_incident_tasks_due_at", table_name="incident_tasks")
    for column in (
        "updated_at", "created_at", "blocked_reason", "verified_at", "verified_by",
        "verification_required", "completed_by", "completed_at", "started_at",
        "created_by", "assigned_role", "priority", "task_type", "description",
        "step_run_id", "playbook_run_id",
    ):
        op.drop_column("incident_tasks", column)
    op.drop_constraint("uq_active_incident_participant_role", "incident_participants", type_="unique")
    for column in ("updated_at", "created_at", "assigned_by", "left_at", "joined_at", "responsibility"):
        op.drop_column("incident_participants", column)
    op.drop_index("ix_operational_incident_sources_source_entity_id", table_name="operational_incident_sources")
    for column in ("created_at", "linked_by", "linked_at", "source_status", "source_entity_type"):
        op.drop_column("operational_incident_sources", column)
    op.drop_constraint("ck_incident_not_self_duplicate", "operational_incidents", type_="check")
    op.drop_index("ix_incident_property_status_created", table_name="operational_incidents")
    op.drop_index("ix_operational_incidents_correlation_key", table_name="operational_incidents")
    op.drop_index("ix_operational_incidents_priority", table_name="operational_incidents")
    op.drop_index("ix_operational_incidents_incident_type", table_name="operational_incidents")
    for column in (
        "updated_at", "updated_by", "last_communication_at", "closed_at", "resolved_at",
        "recovered_at", "mitigated_at", "contained_at", "acknowledged_at", "declared_at",
        "data_quality", "recovery_verified", "closure_reason", "closure_summary",
        "correlation_key", "duplicate_of_id", "linked_ticket_id", "workflow_run_id",
        "playbook_version_id", "playbook_id", "owner_user_id", "life_safety_impact_level",
        "security_impact_level", "department_id", "zone_id", "floor_id", "building_id",
        "device_id", "technology_service_id", "source_reference_id",
        "source_reference_type", "source_type", "organization_id",
    ):
        op.drop_column("operational_incidents", column)
