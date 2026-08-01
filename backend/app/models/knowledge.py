import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def uid():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def now():
    return mapped_column(DateTime(timezone=True), server_default="now()", nullable=False)


class KnowledgeCategory(Base):
    __tablename__ = "knowledge_categories"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_categories.id"))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(140), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class KnowledgeTag(Base):
    __tablename__ = "knowledge_tags"
    id: Mapped[uuid.UUID] = uid()
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now()


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), index=True)
    technology_service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hospitality_technology_services.id"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_categories.id"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    slug: Mapped[str] = mapped_column(String(260), unique=True, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    author_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    owner_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    visibility: Mapped[str] = mapped_column(String(24), default="property", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    approval_state: Mapped[str] = mapped_column(String(24), default="not_submitted")
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archive_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rating_average: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    rating_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()
    __table_args__ = (Index("ix_knowledge_article_property_status_updated", "property_id", "status", "updated_at"),)


class KnowledgeArticleTag(Base):
    __tablename__ = "knowledge_article_tags"
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_tags.id", ondelete="CASCADE"), primary_key=True)


class KnowledgeAttachment(Base):
    __tablename__ = "knowledge_attachments"
    id: Mapped[uuid.UUID] = uid()
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_reference: Mapped[str] = mapped_column(String(500))
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()


class KnowledgeComment(Base):
    __tablename__ = "knowledge_comments"
    id: Mapped[uuid.UUID] = uid()
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_comments.id"))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class KnowledgeRating(Base):
    __tablename__ = "knowledge_ratings"
    id: Mapped[uuid.UUID] = uid()
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    rating: Mapped[int] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("article_id", "user_id", name="uq_knowledge_rating_user_article"),)


class KnowledgeRevision(Base):
    __tablename__ = "knowledge_revisions"
    id: Mapped[uuid.UUID] = uid()
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(240))
    summary: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(Text)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("article_id", "version", name="uq_knowledge_revision_version"),)


class KnowledgeApproval(Base):
    __tablename__ = "knowledge_approvals"
    id: Mapped[uuid.UUID] = uid()
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    revision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_revisions.id"))
    reviewer_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    comments: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    requested_at: Mapped[datetime] = now()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeFavorite(Base):
    __tablename__ = "knowledge_favorites"
    id: Mapped[uuid.UUID] = uid()
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("article_id", "user_id", name="uq_knowledge_favorite_user_article"),)


class KnowledgeViewHistory(Base):
    __tablename__ = "knowledge_view_history"
    id: Mapped[uuid.UUID] = uid()
    article_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    viewed_at: Mapped[datetime] = now()


class Runbook(Base):
    __tablename__ = "runbooks"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    technology_service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hospitality_technology_services.id"))
    name: Mapped[str] = mapped_column(String(180))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    objective: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    owner_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class RunbookVersion(Base):
    __tablename__ = "runbook_versions"
    id: Mapped[uuid.UUID] = uid()
    runbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbooks.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    prerequisites: Mapped[str] = mapped_column(Text, default="[]")
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    safety_notes: Mapped[str] = mapped_column(Text, default="[]")
    required_permissions: Mapped[str] = mapped_column(Text, default="[]")
    rollback_procedure: Mapped[str | None] = mapped_column(Text)
    success_criteria: Mapped[str] = mapped_column(Text, default="[]")
    validation_checklist: Mapped[str] = mapped_column(Text, default="[]")
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    approved_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("runbook_id", "version_number", name="uq_runbook_version"),)


class RunbookStep(Base):
    __tablename__ = "runbook_steps"
    id: Mapped[uuid.UUID] = uid()
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbook_versions.id", ondelete="CASCADE"), index=True)
    step_key: Mapped[str] = mapped_column(String(80))
    sequence_order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    instructions: Mapped[str] = mapped_column(Text)
    step_type: Mapped[str] = mapped_column(String(30), default="manual")
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    verification_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("version_id", "step_key", name="uq_runbook_step_key"),)


class RunbookParameter(Base):
    __tablename__ = "runbook_parameters"
    id: Mapped[uuid.UUID] = uid()
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbook_versions.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(120))
    data_type: Mapped[str] = mapped_column(String(30), default="string")
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    default_value: Mapped[str | None] = mapped_column(Text)
    validation_rule: Mapped[str | None] = mapped_column(String(255))


class RunbookExecution(Base):
    __tablename__ = "runbook_executions"
    id: Mapped[uuid.UUID] = uid()
    runbook_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbooks.id"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbook_versions.id"))
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    incident_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_incidents.id"))
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tickets.id"))
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("automation_workflow_runs.id"))
    status: Mapped[str] = mapped_column(String(30), default="running", index=True)
    parameters: Mapped[str] = mapped_column(Text, default="{}")
    notes: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    started_at: Mapped[datetime] = now()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunbookExecutionStep(Base):
    __tablename__ = "runbook_execution_steps"
    id: Mapped[uuid.UUID] = uid()
    execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbook_executions.id", ondelete="CASCADE"), index=True)
    runbook_step_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbook_steps.id"))
    step_key: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    completed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunbookApproval(Base):
    __tablename__ = "runbook_approvals"
    id: Mapped[uuid.UUID] = uid()
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("runbook_versions.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    comments: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()


class StandardProcedure(Base):
    __tablename__ = "standard_procedures"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    title: Mapped[str] = mapped_column(String(220))
    slug: Mapped[str] = mapped_column(String(240), unique=True)
    procedure_type: Mapped[str] = mapped_column(String(50), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    mandatory_acknowledgement: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    owner_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class ProcedureSection(Base):
    __tablename__ = "procedure_sections"
    id: Mapped[uuid.UUID] = uid()
    procedure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("standard_procedures.id", ondelete="CASCADE"), index=True)
    sequence_order: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str] = mapped_column(String(180))
    body: Mapped[str] = mapped_column(Text)


class ProcedureRevision(Base):
    __tablename__ = "procedure_revisions"
    id: Mapped[uuid.UUID] = uid()
    procedure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("standard_procedures.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[str] = mapped_column(Text)
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()


class ProcedureAcknowledgement(Base):
    __tablename__ = "procedure_acknowledgements"
    id: Mapped[uuid.UUID] = uid()
    procedure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("standard_procedures.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    acknowledged_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("procedure_id", "user_id", "version", name="uq_procedure_ack_version"),)


class ProcedureReview(Base):
    __tablename__ = "procedure_reviews"
    id: Mapped[uuid.UUID] = uid()
    procedure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("standard_procedures.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    notes: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ServiceCatalog(Base):
    __tablename__ = "service_catalogs"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="active")
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class SupportGroup(Base):
    __tablename__ = "support_groups"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class SupportHours(Base):
    __tablename__ = "support_hours"
    id: Mapped[uuid.UUID] = uid()
    support_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("support_groups.id", ondelete="CASCADE"), index=True)
    day_of_week: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[str] = mapped_column(String(8))
    end_time: Mapped[str] = mapped_column(String(8))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")


class CatalogItem(Base):
    __tablename__ = "catalog_items"
    id: Mapped[uuid.UUID] = uid()
    catalog_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("service_catalogs.id", ondelete="CASCADE"), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    technology_service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hospitality_technology_services.id"))
    support_group_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("support_groups.id"))
    name: Mapped[str] = mapped_column(String(180))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str] = mapped_column(Text)
    availability_target: Mapped[float | None] = mapped_column(Float)
    sla_summary: Mapped[str | None] = mapped_column(Text)
    maintenance_window: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class ServiceOwner(Base):
    __tablename__ = "service_owners"
    id: Mapped[uuid.UUID] = uid()
    catalog_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_items.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    owner_role: Mapped[str] = mapped_column(String(40), default="service_owner")
    primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class ServiceDependency(Base):
    __tablename__ = "service_dependencies"
    id: Mapped[uuid.UUID] = uid()
    service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_items.id", ondelete="CASCADE"), index=True)
    depends_on_service_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_items.id", ondelete="CASCADE"), index=True)
    dependency_type: Mapped[str] = mapped_column(String(30), default="required")
    notes: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("service_id", "depends_on_service_id", name="uq_service_dependency"),)


class ServiceRequestTemplate(Base):
    __tablename__ = "service_request_templates"
    id: Mapped[uuid.UUID] = uid()
    catalog_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("catalog_items.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    fields_definition: Mapped[str] = mapped_column(Text, default="[]")
    instructions: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class DocumentFolder(Base):
    __tablename__ = "document_folders"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_folders.id"))
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = now()


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_folders.id"), index=True)
    title: Mapped[str] = mapped_column(String(240))
    slug: Mapped[str] = mapped_column(String(260), unique=True)
    document_type: Mapped[str] = mapped_column(String(50), index=True)
    summary: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    visibility: Mapped[str] = mapped_column(String(24), default="property")
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    owner_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id: Mapped[uuid.UUID] = uid()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_reference: Mapped[str] = mapped_column(String(500))
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    change_summary: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("document_id", "version", name="uq_document_version"),)


class DocumentLink(Base):
    __tablename__ = "document_links"
    id: Mapped[uuid.UUID] = uid()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="related")


class DocumentApproval(Base):
    __tablename__ = "document_approvals"
    id: Mapped[uuid.UUID] = uid()
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_versions.id"))
    reviewer_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    comments: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TroubleshootingGuide(Base):
    __tablename__ = "troubleshooting_guides"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    technology_service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("hospitality_technology_services.id"))
    title: Mapped[str] = mapped_column(String(220))
    slug: Mapped[str] = mapped_column(String(240), unique=True)
    summary: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    verification: Mapped[str | None] = mapped_column(Text)
    escalation_criteria: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class ProblemSignature(Base):
    __tablename__ = "problem_signatures"
    id: Mapped[uuid.UUID] = uid()
    guide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("troubleshooting_guides.id", ondelete="CASCADE"), index=True)
    symptom: Mapped[str] = mapped_column(Text)
    signature_type: Mapped[str] = mapped_column(String(40), default="symptom")
    match_pattern: Mapped[str | None] = mapped_column(String(500))


class ResolutionStep(Base):
    __tablename__ = "resolution_steps"
    id: Mapped[uuid.UUID] = uid()
    guide_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("troubleshooting_guides.id", ondelete="CASCADE"), index=True)
    sequence_order: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(180))
    instructions: Mapped[str] = mapped_column(Text)
    verification: Mapped[str | None] = mapped_column(Text)


class KnownIssue(Base):
    __tablename__ = "known_issues"
    id: Mapped[uuid.UUID] = uid()
    guide_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("troubleshooting_guides.id"), index=True)
    title: Mapped[str] = mapped_column(String(220))
    root_cause: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="known")
    vendor_reference: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = now()


class Workaround(Base):
    __tablename__ = "workarounds"
    id: Mapped[uuid.UUID] = uid()
    known_issue_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("known_issues.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(180))
    instructions: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str | None] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class OperationalChecklistTemplate(Base):
    __tablename__ = "operational_checklist_templates"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    name: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(50), index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    updated_at: Mapped[datetime] = now()


class OperationalChecklistItem(Base):
    __tablename__ = "operational_checklist_template_items"
    id: Mapped[uuid.UUID] = uid()
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_checklist_templates.id", ondelete="CASCADE"), index=True)
    sequence_order: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(String(500))
    required: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    evidence_required: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class OperationalChecklistExecution(Base):
    __tablename__ = "operational_checklist_executions"
    id: Mapped[uuid.UUID] = uid()
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_checklist_templates.id"), index=True)
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    outcome: Mapped[str | None] = mapped_column(String(20))
    comments: Mapped[str | None] = mapped_column(Text)
    started_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    started_at: Mapped[datetime] = now()
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationalChecklistExecutionItem(Base):
    __tablename__ = "operational_checklist_execution_items"
    id: Mapped[uuid.UUID] = uid()
    execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_checklist_executions.id", ondelete="CASCADE"), index=True)
    template_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("operational_checklist_template_items.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    comments: Mapped[str | None] = mapped_column(Text)
    completed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class KnowledgeRelationship(Base):
    __tablename__ = "knowledge_relationships"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(40), index=True)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    target_type: Mapped[str] = mapped_column(String(40), index=True)
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    relationship_type: Mapped[str] = mapped_column(String(40), default="related")
    notes: Mapped[str | None] = mapped_column(Text)
    validation_status: Mapped[str] = mapped_column(String(20), default="unchecked", index=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()
    __table_args__ = (UniqueConstraint("source_type", "source_id", "target_type", "target_id", "relationship_type", name="uq_knowledge_relationship"),)


class KnowledgeSearchStat(Base):
    __tablename__ = "knowledge_search_stats"
    id: Mapped[uuid.UUID] = uid()
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True)
    user_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id"))
    query_text: Mapped[str] = mapped_column(String(240))
    filters: Mapped[str] = mapped_column(Text, default="{}")
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    searched_at: Mapped[datetime] = now()
