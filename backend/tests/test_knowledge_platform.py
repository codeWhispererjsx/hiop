from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from fastapi.testclient import TestClient

from app.api.v1.knowledge import AttachmentWrite, ArticleWrite, printable_pdf, router
from app.main import app
from app.models import knowledge
from app.services.knowledge_service import ARTICLE_TRANSITIONS, checksum, safe_markdown, slugify
from app.services.scheduler_service import KNOWLEDGE_JOB_INTERVALS, knowledge_job_id


def test_epic_3d_domain_models_are_registered():
    names = {
        "KnowledgeArticle", "KnowledgeCategory", "KnowledgeTag", "KnowledgeAttachment",
        "KnowledgeComment", "KnowledgeRating", "KnowledgeRevision", "KnowledgeApproval",
        "KnowledgeFavorite", "KnowledgeViewHistory", "Runbook", "RunbookVersion",
        "RunbookStep", "RunbookParameter", "RunbookExecution", "RunbookExecutionStep",
        "RunbookApproval", "StandardProcedure", "ProcedureSection", "ProcedureRevision",
        "ProcedureAcknowledgement", "ProcedureReview", "ServiceCatalog", "CatalogItem",
        "ServiceOwner", "SupportGroup", "SupportHours", "ServiceDependency",
        "ServiceRequestTemplate", "Document", "DocumentFolder", "DocumentVersion",
        "DocumentLink", "DocumentApproval", "TroubleshootingGuide", "ProblemSignature",
        "ResolutionStep", "KnownIssue", "Workaround", "OperationalChecklistTemplate",
        "OperationalChecklistExecution", "KnowledgeRelationship", "KnowledgeSearchStat",
    }
    assert all(hasattr(knowledge, name) for name in names)
    assert len({getattr(knowledge, name).__tablename__ for name in names}) == len(names)


def test_article_lifecycle_is_controlled_and_requires_review():
    assert ARTICLE_TRANSITIONS["draft"] == {"in_review"}
    assert "published" not in ARTICLE_TRANSITIONS["draft"]
    assert ARTICLE_TRANSITIONS["approved"] == {"published", "draft"}
    assert ARTICLE_TRANSITIONS["archived"] == {"draft"}


def test_markdown_rejects_active_content_and_slug_is_deterministic():
    assert safe_markdown("# Safe\nUse `show version` as reviewed documentation.").startswith("# Safe")
    with pytest.raises(HTTPException, match="Executable"):
        safe_markdown("<script>alert(1)</script>")
    with pytest.raises(HTTPException, match="Executable"):
        safe_markdown("[click](javascript:alert(1))")
    assert slugify("Opera PMS — Recovery Guide") == "opera-pms-recovery-guide"
    assert checksum("a", "b") == checksum("a", "b")


def test_attachment_metadata_is_bounded_and_traversal_free():
    valid = AttachmentWrite(
        filename="guide.pdf", media_type="application/pdf", size_bytes=10,
        storage_reference="knowledge/guide.pdf", checksum_sha256="a" * 64,
    )
    assert valid.size_bytes == 10
    with pytest.raises(ValidationError):
        AttachmentWrite(filename="x", media_type="application/x-executable", size_bytes=10, storage_reference="../x", checksum_sha256="a" * 64)
    with pytest.raises(ValidationError):
        AttachmentWrite(filename="x", media_type="application/pdf", size_bytes=25_000_001, storage_reference="x", checksum_sha256="a" * 64)


def test_article_schema_keeps_markdown_and_visibility_bounded():
    row = ArticleWrite(title="Daily WiFi checks", body="# Checklist", visibility="property")
    assert row.body == "# Checklist"
    with pytest.raises(ValidationError):
        ArticleWrite(title="Unsafe", body="<iframe src='x'></iframe>")
    with pytest.raises(ValidationError):
        ArticleWrite(title="Visibility", body="safe", visibility="public")


def test_knowledge_scheduler_jobs_are_stable_separate_and_complete():
    expected = {"scheduled_lifecycle", "review_reminders", "expired_documents", "broken_links", "revision_reminders", "statistics", "search_index"}
    assert expected == set(KNOWLEDGE_JOB_INTERVALS)
    assert knowledge_job_id("scheduled_lifecycle") == "knowledge_scheduled_lifecycle"
    with pytest.raises(ValueError):
        knowledge_job_id("arbitrary")


def test_api_surface_covers_requested_workspaces_and_exports():
    paths = {route.path for route in router.routes if getattr(route, "path", None)}
    expected = {
        "/knowledge/dashboard", "/knowledge/articles", "/knowledge/articles/{article_id}",
        "/knowledge/articles/{article_id}/revisions", "/knowledge/articles/{article_id}/rating",
        "/knowledge/favorites", "/knowledge/recent", "/knowledge/categories", "/knowledge/tags",
        "/knowledge/approvals", "/knowledge/runbooks", "/knowledge/runbooks/{runbook_id}/execute",
        "/knowledge/runbook-executions/{execution_id}/steps/{step_id}/complete",
        "/knowledge/sops", "/knowledge/sops/{procedure_id}/acknowledge",
        "/knowledge/service-catalogs", "/knowledge/documents", "/knowledge/troubleshooting",
        "/knowledge/checklists", "/knowledge/search", "/knowledge/relationships",
        "/knowledge/reports/summary", "/knowledge/reports/export", "/knowledge/audit-history",
    }
    assert expected.issubset(paths)
    assert not any("webhook" in path or "ai" in path for path in paths)


def test_search_models_have_property_and_time_indexes():
    assert knowledge.KnowledgeArticle.__table__.c.property_id.index
    assert knowledge.KnowledgeArticle.__table__.c.status.index
    assert knowledge.KnowledgeArticle.__table__.c.publish_at.index
    assert knowledge.KnowledgeRelationship.__table__.c.source_id.index
    assert knowledge.KnowledgeRelationship.__table__.c.validation_status.index


def test_report_pdf_has_valid_catalog_font_xref_and_eof():
    output = printable_pdf("Knowledge", ["Safe report row"])
    assert output.startswith(b"%PDF-1.4")
    assert b"/Type /Catalog" in output
    assert b"/BaseFont /Helvetica" in output
    assert b"xref" in output
    assert output.endswith(b"%%EOF\n")


def test_knowledge_routes_require_authentication():
    client = TestClient(app)
    assert client.get("/api/v1/knowledge/dashboard").status_code == 401
    assert client.post("/api/v1/knowledge/articles", json={}).status_code == 401


def test_management_routes_include_safe_update_and_retire_operations():
    operations = {(route.path, method) for route in router.routes for method in getattr(route, "methods", set())}
    for resource in ("categories", "tags", "runbooks", "sops", "service-catalogs", "catalog-items", "documents", "troubleshooting", "checklists"):
        assert (f"/knowledge/{resource}/{{entity_id}}", "PATCH") in operations
        assert (f"/knowledge/{resource}/{{entity_id}}", "DELETE") in operations
