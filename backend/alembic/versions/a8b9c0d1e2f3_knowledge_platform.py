"""knowledge base, runbooks, service catalog, and operational documentation

Revision ID: a8b9c0d1e2f3
Revises: f6d7e8f9a0b1
"""
from alembic import op

revision = "a8b9c0d1e2f3"
down_revision = "f6d7e8f9a0b1"
branch_labels = None
depends_on = None


TABLES = (
    "knowledge_categories", "knowledge_tags", "knowledge_articles",
    "knowledge_article_tags", "knowledge_attachments", "knowledge_comments",
    "knowledge_ratings", "knowledge_revisions", "knowledge_approvals",
    "knowledge_favorites", "knowledge_view_history", "runbooks",
    "runbook_versions", "runbook_steps", "runbook_parameters",
    "runbook_executions", "runbook_execution_steps", "runbook_approvals",
    "standard_procedures", "procedure_sections", "procedure_revisions",
    "procedure_acknowledgements", "procedure_reviews", "service_catalogs",
    "support_groups", "support_hours", "catalog_items", "service_owners",
    "service_dependencies", "service_request_templates", "document_folders",
    "documents", "document_versions", "document_links", "document_approvals",
    "troubleshooting_guides", "problem_signatures", "resolution_steps",
    "known_issues", "workarounds", "operational_checklist_templates",
    "operational_checklist_template_items", "operational_checklist_executions",
    "operational_checklist_execution_items", "knowledge_relationships",
    "knowledge_search_stats",
)


def upgrade():
    from app.models import hospitality_operations  # noqa: F401
    from app.models import knowledge  # noqa: F401
    from app.db.database import Base
    bind = op.get_bind()
    for table_name in TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_knowledge_articles_fts ON knowledge_articles USING gin (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(summary,'') || ' ' || coalesce(body,'')))")
        op.execute("CREATE INDEX IF NOT EXISTS ix_documents_fts ON documents USING gin (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(summary,'')))")
        op.execute("CREATE INDEX IF NOT EXISTS ix_troubleshooting_guides_fts ON troubleshooting_guides USING gin (to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(summary,'')))")


def downgrade():
    for table_name in reversed(TABLES):
        op.drop_table(table_name)
