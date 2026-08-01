import csv
import io
import json
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.hierarchy import Property
from app.models.audit_log import AuditLog
from app.models.knowledge import (
    CatalogItem, Document, DocumentApproval, DocumentFolder, DocumentLink,
    DocumentVersion, KnowledgeApproval, KnowledgeArticle, KnowledgeArticleTag,
    KnowledgeAttachment, KnowledgeCategory, KnowledgeComment, KnowledgeFavorite,
    KnowledgeRating, KnowledgeRelationship, KnowledgeRevision, KnowledgeSearchStat,
    KnowledgeTag, KnowledgeViewHistory, KnownIssue, OperationalChecklistExecution,
    OperationalChecklistExecutionItem, OperationalChecklistItem,
    OperationalChecklistTemplate, ProblemSignature, ProcedureAcknowledgement,
    ProcedureReview, ProcedureRevision, ProcedureSection, ResolutionStep, Runbook,
    RunbookApproval, RunbookExecution, RunbookExecutionStep, RunbookParameter,
    RunbookStep, RunbookVersion, ServiceCatalog, ServiceDependency, ServiceOwner,
    ServiceRequestTemplate, StandardProcedure, SupportGroup, SupportHours,
    TroubleshootingGuide, Workaround,
)
from app.models.property_access import UserPropertyAccess
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager
from app.services.knowledge_service import (
    checksum, complete_runbook_step, rate_article, record_view, rollback_article,
    safe_markdown, search_knowledge, slugify, snapshot_article, start_runbook,
    transition_article,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Management"])
reader = require_roles(["admin", "superadmin", "technician", "viewer"])
contributor = require_roles(["admin", "superadmin", "technician"])
publisher = require_roles(["admin", "superadmin"])


def validate_markdown_field(value: str, maximum: int = 200_000) -> str:
    try:
        return safe_markdown(value, maximum)
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc


class ArticleWrite(BaseModel):
    property_id: UUID | None = None
    department_id: UUID | None = None
    technology_service_id: UUID | None = None
    category_id: UUID | None = None
    title: str = Field(min_length=3, max_length=240)
    slug: str | None = Field(None, max_length=260)
    summary: str | None = Field(None, max_length=4000)
    body: str = Field("", max_length=200000)
    owner_id: str | None = None
    visibility: str = Field("property", pattern=r"^(corporate|property|department|restricted)$")
    publish_at: datetime | None = None
    archive_at: datetime | None = None
    next_review_at: datetime | None = None
    tag_ids: list[UUID] = Field(default_factory=list, max_length=30)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value):
        return validate_markdown_field(value)


class ArticlePatch(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=240)
    summary: str | None = Field(None, max_length=4000)
    body: str | None = Field(None, max_length=200000)
    category_id: UUID | None = None
    department_id: UUID | None = None
    technology_service_id: UUID | None = None
    owner_id: str | None = None
    visibility: str | None = Field(None, pattern=r"^(corporate|property|department|restricted)$")
    publish_at: datetime | None = None
    archive_at: datetime | None = None
    next_review_at: datetime | None = None
    tag_ids: list[UUID] | None = Field(None, max_length=30)
    change_summary: str = Field("Article updated", max_length=1000)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value):
        return validate_markdown_field(value) if value is not None else value


class NamedWrite(BaseModel):
    property_id: UUID | None = None
    name: str = Field(min_length=2, max_length=180)
    slug: str | None = None
    description: str | None = Field(None, max_length=10000)


class CommentWrite(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    parent_id: UUID | None = None


class RatingWrite(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback: str | None = Field(None, max_length=2000)


class LifecycleWrite(BaseModel):
    comments: str | None = Field(None, max_length=5000)


class AttachmentWrite(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(max_length=120)
    size_bytes: int = Field(gt=0, le=25_000_000)
    storage_reference: str = Field(max_length=500)
    checksum_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")

    @field_validator("storage_reference")
    @classmethod
    def safe_reference(cls, value):
        if value.startswith(("/", "\\")) or ".." in value.replace("\\", "/").split("/"):
            raise ValueError("storage reference must be relative and traversal-free")
        return value

    @field_validator("media_type")
    @classmethod
    def safe_media(cls, value):
        allowed = {"application/pdf", "text/markdown", "image/png", "image/jpeg", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/vnd.ms-visio.drawing.main+xml"}
        if value not in allowed:
            raise ValueError("unsupported document media type")
        return value


class RunbookWrite(BaseModel):
    property_id: UUID | None = None
    technology_service_id: UUID | None = None
    name: str = Field(min_length=3, max_length=180)
    slug: str | None = None
    objective: str = Field(min_length=3, max_length=10000)
    owner_id: str | None = None


class RunbookVersionWrite(BaseModel):
    prerequisites: list[str] = Field(default_factory=list, max_length=100)
    estimated_duration_minutes: int | None = Field(None, ge=1, le=10080)
    safety_notes: list[str] = Field(default_factory=list, max_length=100)
    required_permissions: list[str] = Field(default_factory=list, max_length=50)
    rollback_procedure: str | None = Field(None, max_length=20000)
    success_criteria: list[str] = Field(default_factory=list, max_length=100)
    validation_checklist: list[str] = Field(default_factory=list, max_length=100)
    change_summary: str | None = Field(None, max_length=2000)


class RunbookStepWrite(BaseModel):
    step_key: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    sequence_order: int = Field(ge=0, le=1000)
    title: str = Field(min_length=2, max_length=180)
    instructions: str = Field(min_length=1, max_length=20000)
    step_type: str = Field("manual", pattern=r"^(manual|checklist|verification|decision|communication)$")
    evidence_required: bool = False
    verification_required: bool = False


class RunbookStartWrite(BaseModel):
    property_id: UUID | None = None
    parameters: dict = Field(default_factory=dict)
    incident_id: UUID | None = None
    ticket_id: UUID | None = None
    workflow_run_id: UUID | None = None


class StepCompleteWrite(BaseModel):
    notes: str | None = Field(None, max_length=10000)
    evidence_reference: str | None = Field(None, max_length=500)


class SOPWrite(BaseModel):
    property_id: UUID | None = None
    title: str = Field(min_length=3, max_length=220)
    slug: str | None = None
    procedure_type: str = Field(max_length=50)
    summary: str | None = Field(None, max_length=5000)
    mandatory_acknowledgement: bool = False
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    next_review_at: datetime | None = None
    owner_id: str | None = None


class SectionWrite(BaseModel):
    sequence_order: int = Field(ge=0, le=1000)
    heading: str = Field(max_length=180)
    body: str = Field(max_length=50000)

    @field_validator("body")
    @classmethod
    def safe_body(cls, value): return validate_markdown_field(value, 50000)


class CatalogItemWrite(BaseModel):
    property_id: UUID | None = None
    technology_service_id: UUID | None = None
    support_group_id: UUID | None = None
    name: str = Field(min_length=2, max_length=180)
    slug: str | None = None
    description: str = Field(max_length=10000)
    availability_target: float | None = Field(None, ge=0, le=100)
    sla_summary: str | None = Field(None, max_length=5000)
    maintenance_window: str | None = Field(None, max_length=255)


class DocumentWrite(BaseModel):
    property_id: UUID | None = None
    folder_id: UUID | None = None
    title: str = Field(min_length=3, max_length=240)
    slug: str | None = None
    document_type: str = Field(max_length=50)
    summary: str | None = Field(None, max_length=5000)
    visibility: str = Field("property", pattern=r"^(corporate|property|department|restricted)$")
    owner_id: str | None = None
    next_review_at: datetime | None = None
    expires_at: datetime | None = None


class GuideWrite(BaseModel):
    property_id: UUID | None = None
    technology_service_id: UUID | None = None
    title: str = Field(min_length=3, max_length=220)
    slug: str | None = None
    summary: str | None = Field(None, max_length=5000)
    severity: str = Field("medium", pattern=r"^(informational|low|medium|high|critical)$")
    verification: str | None = Field(None, max_length=10000)
    escalation_criteria: str | None = Field(None, max_length=10000)


class ChecklistWrite(BaseModel):
    property_id: UUID | None = None
    name: str = Field(min_length=3, max_length=180)
    description: str | None = Field(None, max_length=5000)
    category: str = Field(max_length=50)
    evidence_required: bool = False


class ChecklistItemWrite(BaseModel):
    sequence_order: int = Field(ge=0, le=1000)
    text: str = Field(min_length=2, max_length=500)
    required: bool = True
    evidence_required: bool = False


class RelationshipWrite(BaseModel):
    property_id: UUID | None = None
    source_type: str = Field(max_length=40)
    source_id: UUID
    target_type: str = Field(max_length=40)
    target_id: UUID
    relationship_type: str = Field("related", max_length=40)
    notes: str | None = Field(None, max_length=5000)


class ManagementPatch(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=240)
    title: str | None = Field(None, min_length=2, max_length=240)
    description: str | None = Field(None, max_length=10000)
    summary: str | None = Field(None, max_length=10000)
    status: str | None = Field(None, max_length=30)
    enabled: bool | None = None

    @field_validator("status")
    @classmethod
    def safe_status(cls, value):
        allowed = {"draft", "in_review", "approved", "published", "archived", "active", "inactive", "expired", "known", "resolved"}
        if value is not None and value not in allowed: raise ValueError("unsupported managed status")
        return value


def allowed_properties(db, user):
    if user.role in {"admin", "superadmin"}:
        return None
    return [row.property_id for row in db.query(UserPropertyAccess).filter_by(user_id=user.id, enabled=True).all()]


def require_property(db, user, property_id):
    if property_id is None:
        if user.role not in {"admin", "superadmin"}:
            raise HTTPException(403, "Corporate knowledge requires administrator access")
        return
    if not db.get(Property, property_id):
        raise HTTPException(404, "Property not found")
    allowed = allowed_properties(db, user)
    if allowed is not None and property_id not in allowed:
        raise HTTPException(403, "Property is not authorized")


def scoped(query, column, db, user):
    allowed = allowed_properties(db, user)
    return query if allowed is None else query.filter(or_(column.is_(None), column.in_(allowed)))


def article_or_404(db, user, article_id, count_view=False):
    article = db.get(KnowledgeArticle, article_id)
    if not article:
        raise HTTPException(404, "Knowledge article not found")
    require_property(db, user, article.property_id)
    if article.visibility == "restricted" and user.role not in {"admin", "superadmin", "technician"}:
        raise HTTPException(403, "Restricted article")
    if count_view:
        record_view(db, article, user.id)
        db.commit()
    return article


def commit_audit(db, user, action, entity, row, message):
    create_audit_log(db, user.username, action, entity, str(row.id), message)
    db.commit(); db.refresh(row)
    manager.broadcast_from_thread({"type": "knowledge_record_updated", "entity_type": entity, "entity_id": str(row.id), "action": action, "property_id": str(getattr(row, "property_id", "")) or None})
    return row


def replace_tags(db, article, tag_ids):
    db.query(KnowledgeArticleTag).filter_by(article_id=article.id).delete()
    for tag_id in dict.fromkeys(tag_ids):
        if not db.get(KnowledgeTag, tag_id):
            raise HTTPException(422, f"Unknown tag: {tag_id}")
        db.add(KnowledgeArticleTag(article_id=article.id, tag_id=tag_id))


def update_managed(db, user, model, entity_id, payload, entity_name):
    row = db.get(model, entity_id)
    if not row: raise HTTPException(404, f"{entity_name} not found")
    if hasattr(row, "property_id"): require_property(db, user, row.property_id)
    values = payload.model_dump(exclude_unset=True)
    if "status" in values and model in {Runbook, StandardProcedure, Document, TroubleshootingGuide, OperationalChecklistTemplate}:
        raise HTTPException(409, "Use the reviewed lifecycle action to change status")
    for key, value in values.items():
        if hasattr(row, key): setattr(row, key, value)
    if hasattr(row, "updated_at"): row.updated_at = datetime.now(timezone.utc)
    return commit_audit(db, user, f"{entity_name.upper()}_UPDATED", entity_name, row, f"Updated {entity_name}")


def retire_managed(db, user, model, entity_id, entity_name):
    row = db.get(model, entity_id)
    if not row: raise HTTPException(404, f"{entity_name} not found")
    if hasattr(row, "property_id"): require_property(db, user, row.property_id)
    if hasattr(row, "status"): row.status = "archived"
    elif hasattr(row, "enabled"): row.enabled = False
    else: db.delete(row)
    create_audit_log(db, user.username, f"{entity_name.upper()}_RETIRED", entity_name, str(entity_id), f"Safely retired {entity_name}")
    db.commit()
    return Response(status_code=204)


def printable_pdf(title: str, lines: list[str]) -> bytes:
    """Build a small, valid, deterministic PDF without a new runtime dependency."""
    escaped = []
    for line in [title, "", *lines[:45]]:
        value = str(line).encode("latin-1", "replace").decode("latin-1")
        escaped.append(value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)"))
    commands = ["BT", "/F1 10 Tf", "40 760 Td", "13 TL"]
    for index, line in enumerate(escaped):
        if index: commands.append("T*")
        commands.append(f"({line[:150]}) Tj")
    commands.append("ET")
    stream = "\n".join(commands).encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, value in enumerate(objects, 1):
        offsets.append(len(output)); output.extend(f"{number} 0 obj\n".encode()); output.extend(value); output.extend(b"\nendobj\n")
    xref = len(output); output.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]: output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user=Depends(reader)):
    articles = scoped(db.query(KnowledgeArticle), KnowledgeArticle.property_id, db, user)
    runbooks = scoped(db.query(Runbook), Runbook.property_id, db, user)
    procedures = scoped(db.query(StandardProcedure), StandardProcedure.property_id, db, user)
    documents = scoped(db.query(Document), Document.property_id, db, user)
    now = datetime.now(timezone.utc)
    return {"articles": articles.count(), "published_articles": articles.filter_by(status="published").count(), "approval_backlog": articles.filter_by(status="in_review").count(), "runbooks": runbooks.count(), "sops": procedures.count(), "documents": documents.count(), "outdated": articles.filter(KnowledgeArticle.next_review_at < now).count(), "recent": articles.order_by(desc(KnowledgeArticle.updated_at)).limit(8).all()}


@router.get("/articles")
def list_articles(search: str | None = None, status: str | None = None, property_id: UUID | None = None, category_id: UUID | None = None, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user=Depends(reader)):
    query = scoped(db.query(KnowledgeArticle), KnowledgeArticle.property_id, db, user)
    if search: query = query.filter(or_(KnowledgeArticle.title.ilike(f"%{search[:120]}%"), KnowledgeArticle.summary.ilike(f"%{search[:120]}%")))
    if status: query = query.filter_by(status=status)
    if property_id: require_property(db, user, property_id); query = query.filter_by(property_id=property_id)
    if category_id: query = query.filter_by(category_id=category_id)
    total = query.count(); items = query.order_by(desc(KnowledgeArticle.updated_at)).offset((page-1)*page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.post("/articles", status_code=201)
def create_article(payload: ArticleWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id)
    slug = payload.slug or slugify(payload.title)
    if db.query(KnowledgeArticle).filter_by(slug=slug).first(): raise HTTPException(409, "Article slug already exists")
    data = payload.model_dump(exclude={"tag_ids"}); data["slug"] = slug
    article = KnowledgeArticle(**data, author_id=user.id, status="draft")
    db.add(article); db.flush(); replace_tags(db, article, payload.tag_ids); snapshot_article(db, article, user.username, "Initial draft")
    return commit_audit(db, user, "KNOWLEDGE_ARTICLE_CREATED", "KnowledgeArticle", article, "Created article draft")


@router.get("/articles/{article_id}")
def get_article(article_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    return article_or_404(db, user, article_id, True)


@router.patch("/articles/{article_id}")
def update_article(article_id: UUID, payload: ArticlePatch, db: Session = Depends(get_db), user=Depends(contributor)):
    article = article_or_404(db, user, article_id)
    if article.status != "draft": raise HTTPException(409, "Only draft articles can be edited")
    snapshot_article(db, article, user.username, payload.change_summary)
    values = payload.model_dump(exclude_unset=True, exclude={"tag_ids", "change_summary"})
    for key, value in values.items(): setattr(article, key, value)
    if payload.tag_ids is not None: replace_tags(db, article, payload.tag_ids)
    article.updated_at = datetime.now(timezone.utc)
    return commit_audit(db, user, "KNOWLEDGE_ARTICLE_UPDATED", "KnowledgeArticle", article, payload.change_summary)


@router.post("/articles/{article_id}/{action}")
def article_action(article_id: UUID, action: str, payload: LifecycleWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    article = article_or_404(db, user, article_id)
    targets = {"submit-review": "in_review", "return-draft": "draft", "approve": "approved", "publish": "published", "archive": "archived"}
    target = targets.get(action)
    if not target: raise HTTPException(404, "Unsupported article action")
    if action in {"approve", "publish", "archive"} and user.role not in {"admin", "superadmin"}: raise HTTPException(403, "Publisher permission required")
    transition_article(db, article, target, user.username, payload.comments); db.commit(); return article


@router.get("/articles/{article_id}/revisions")
def revisions(article_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    article_or_404(db, user, article_id)
    return {"items": db.query(KnowledgeRevision).filter_by(article_id=article_id).order_by(desc(KnowledgeRevision.version)).all()}


@router.get("/articles/{article_id}/revisions/compare")
def compare_revisions(article_id: UUID, from_version: int, to_version: int, db: Session = Depends(get_db), user=Depends(reader)):
    article_or_404(db, user, article_id)
    rows = db.query(KnowledgeRevision).filter(KnowledgeRevision.article_id == article_id, KnowledgeRevision.version.in_((from_version, to_version))).all()
    mapping = {row.version: row for row in rows}
    if from_version not in mapping or to_version not in mapping: raise HTTPException(404, "Revision not found")
    before, after = mapping[from_version], mapping[to_version]
    return {"from_version": from_version, "to_version": to_version, "title_changed": before.title != after.title, "summary_changed": before.summary != after.summary, "body_changed": before.body != after.body, "before_checksum": before.checksum_sha256, "after_checksum": after.checksum_sha256}


@router.post("/articles/{article_id}/revisions/{revision_id}/rollback")
def rollback_revision(article_id: UUID, revision_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    article = article_or_404(db, user, article_id); revision = db.query(KnowledgeRevision).filter_by(id=revision_id, article_id=article_id).first()
    if not revision: raise HTTPException(404, "Revision not found")
    rollback_article(db, article, revision, user.username); db.commit(); return article


@router.get("/articles/{article_id}/comments")
def comments(article_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    article_or_404(db, user, article_id); return {"items": db.query(KnowledgeComment).filter_by(article_id=article_id).order_by(KnowledgeComment.created_at).all()}


@router.post("/articles/{article_id}/comments", status_code=201)
def add_comment(article_id: UUID, payload: CommentWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    article_or_404(db, user, article_id); row = KnowledgeComment(article_id=article_id, user_id=user.id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@router.post("/articles/{article_id}/rating")
def set_rating(article_id: UUID, payload: RatingWrite, db: Session = Depends(get_db), user=Depends(reader)):
    article = article_or_404(db, user, article_id); row = rate_article(db, article, user.id, payload.rating, payload.feedback); db.commit(); return row


@router.post("/articles/{article_id}/favorite")
def toggle_favorite(article_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    article_or_404(db, user, article_id); row = db.query(KnowledgeFavorite).filter_by(article_id=article_id, user_id=user.id).first()
    if row: db.delete(row); active = False
    else: db.add(KnowledgeFavorite(article_id=article_id, user_id=user.id)); active = True
    db.commit(); return {"favorite": active}


@router.get("/favorites")
def favorites(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": db.query(KnowledgeArticle).join(KnowledgeFavorite).filter(KnowledgeFavorite.user_id == user.id).order_by(desc(KnowledgeFavorite.created_at)).limit(100).all()}


@router.get("/recent")
def recent(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": db.query(KnowledgeArticle).join(KnowledgeViewHistory).filter(KnowledgeViewHistory.user_id == user.id).order_by(desc(KnowledgeViewHistory.viewed_at)).limit(50).all()}


@router.post("/articles/{article_id}/attachments", status_code=201)
def add_attachment(article_id: UUID, payload: AttachmentWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    article_or_404(db, user, article_id); row = KnowledgeAttachment(article_id=article_id, uploaded_by=user.id, **payload.model_dump()); db.add(row); return commit_audit(db, user, "KNOWLEDGE_ATTACHMENT_ADDED", "KnowledgeAttachment", row, "Added bounded attachment metadata")


@router.get("/categories")
def categories(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": scoped(db.query(KnowledgeCategory), KnowledgeCategory.property_id, db, user).order_by(KnowledgeCategory.name).all()}


@router.post("/categories", status_code=201)
def create_category(payload: NamedWrite, db: Session = Depends(get_db), user=Depends(publisher)):
    require_property(db, user, payload.property_id); row = KnowledgeCategory(property_id=payload.property_id, name=payload.name, slug=payload.slug or slugify(payload.name), description=payload.description); db.add(row); return commit_audit(db, user, "KNOWLEDGE_CATEGORY_CREATED", "KnowledgeCategory", row, "Created category")


@router.get("/tags")
def tags(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": db.query(KnowledgeTag).order_by(KnowledgeTag.name).all()}


@router.post("/tags", status_code=201)
def create_tag(payload: NamedWrite, db: Session = Depends(get_db), user=Depends(publisher)):
    row = KnowledgeTag(name=payload.name, slug=payload.slug or slugify(payload.name), description=payload.description); db.add(row); return commit_audit(db, user, "KNOWLEDGE_TAG_CREATED", "KnowledgeTag", row, "Created tag")


@router.get("/approvals")
def approvals(status: str | None = None, db: Session = Depends(get_db), user=Depends(contributor)):
    query = db.query(KnowledgeApproval).join(KnowledgeArticle); query = scoped(query, KnowledgeArticle.property_id, db, user)
    if status: query = query.filter(KnowledgeApproval.status == status)
    return {"items": query.order_by(desc(KnowledgeApproval.requested_at)).limit(200).all()}


@router.get("/runbooks")
def list_runbooks(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": scoped(db.query(Runbook), Runbook.property_id, db, user).order_by(Runbook.name).all()}


@router.post("/runbooks", status_code=201)
def create_runbook(payload: RunbookWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id); row = Runbook(**payload.model_dump(exclude={"slug"}), slug=payload.slug or slugify(payload.name), created_by=user.id); db.add(row); return commit_audit(db, user, "RUNBOOK_CREATED", "Runbook", row, "Created runbook")


@router.get("/runbooks/{runbook_id}")
def get_runbook(runbook_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    row = db.get(Runbook, runbook_id)
    if not row: raise HTTPException(404, "Runbook not found")
    require_property(db, user, row.property_id); return row


@router.post("/runbooks/{runbook_id}/versions", status_code=201)
def create_runbook_version(runbook_id: UUID, payload: RunbookVersionWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    runbook = get_runbook(runbook_id, db, user); number = (db.query(func.max(RunbookVersion.version_number)).filter_by(runbook_id=runbook.id).scalar() or 0) + 1
    data = payload.model_dump();
    for key in ("prerequisites", "safety_notes", "required_permissions", "success_criteria", "validation_checklist"): data[key] = json.dumps(data[key])
    row = RunbookVersion(runbook_id=runbook.id, version_number=number, created_by=user.id, **data); db.add(row); return commit_audit(db, user, "RUNBOOK_VERSION_CREATED", "RunbookVersion", row, f"Created runbook version {number}")


@router.get("/runbooks/{runbook_id}/versions")
def runbook_versions(runbook_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    get_runbook(runbook_id, db, user); return {"items": db.query(RunbookVersion).filter_by(runbook_id=runbook_id).order_by(desc(RunbookVersion.version_number)).all()}


@router.post("/runbook-versions/{version_id}/steps", status_code=201)
def create_runbook_step(version_id: UUID, payload: RunbookStepWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    version = db.get(RunbookVersion, version_id)
    if not version: raise HTTPException(404, "Runbook version not found")
    get_runbook(version.runbook_id, db, user)
    if version.status != "draft": raise HTTPException(409, "Approved versions are immutable")
    row = RunbookStep(version_id=version.id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@router.get("/runbook-versions/{version_id}/steps")
def runbook_steps(version_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    version = db.get(RunbookVersion, version_id)
    if not version: raise HTTPException(404, "Runbook version not found")
    get_runbook(version.runbook_id, db, user); return {"items": db.query(RunbookStep).filter_by(version_id=version_id).order_by(RunbookStep.sequence_order).all()}


@router.post("/runbook-versions/{version_id}/submit-review")
def submit_runbook(version_id: UUID, db: Session = Depends(get_db), user=Depends(contributor)):
    version = db.get(RunbookVersion, version_id)
    if not version or version.status != "draft": raise HTTPException(409, "Draft runbook version required")
    runbook = get_runbook(version.runbook_id, db, user); steps = db.query(RunbookStep).filter_by(version_id=version.id).order_by(RunbookStep.sequence_order).all()
    if not steps: raise HTTPException(409, "At least one runbook step is required")
    version.checksum_sha256 = checksum(version.prerequisites, version.safety_notes, version.rollback_procedure, *[f"{s.step_key}:{s.instructions}" for s in steps]); version.status = "in_review"; db.add(RunbookApproval(version_id=version.id, status="pending")); return commit_audit(db, user, "RUNBOOK_SUBMITTED", "RunbookVersion", version, f"Submitted {runbook.name}")


@router.post("/runbook-versions/{version_id}/approve")
def approve_runbook(version_id: UUID, payload: LifecycleWrite, db: Session = Depends(get_db), user=Depends(publisher)):
    version = db.get(RunbookVersion, version_id)
    if not version or version.status != "in_review": raise HTTPException(409, "Runbook version is not in review")
    runbook = get_runbook(version.runbook_id, db, user); version.status, version.approved_by, version.approved_at = "approved", user.id, datetime.now(timezone.utc); runbook.current_version_id, runbook.status = version.id, "published"; approval = db.query(RunbookApproval).filter_by(version_id=version.id, status="pending").first(); approval.status, approval.reviewer_id, approval.comments, approval.decided_at = "approved", user.id, payload.comments, datetime.now(timezone.utc); return commit_audit(db, user, "RUNBOOK_VERSION_APPROVED", "RunbookVersion", version, "Approved immutable runbook version")


@router.post("/runbooks/{runbook_id}/execute", status_code=201)
def execute_runbook(runbook_id: UUID, payload: RunbookStartWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    runbook = get_runbook(runbook_id, db, user); require_property(db, user, payload.property_id or runbook.property_id); version = db.get(RunbookVersion, runbook.current_version_id) if runbook.current_version_id else None
    if not version: raise HTTPException(409, "No active runbook version")
    execution = start_runbook(db, runbook, version, user.id, payload.property_id or runbook.property_id, payload.parameters, payload.model_dump()); db.commit(); db.refresh(execution); return execution


@router.get("/runbook-executions")
def executions(status: str | None = None, db: Session = Depends(get_db), user=Depends(reader)):
    query = scoped(db.query(RunbookExecution), RunbookExecution.property_id, db, user)
    if status: query = query.filter_by(status=status)
    return {"items": query.order_by(desc(RunbookExecution.started_at)).limit(200).all()}


@router.get("/runbook-executions/{execution_id}/steps")
def execution_steps(execution_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    execution = db.get(RunbookExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    require_property(db, user, execution.property_id); return {"items": db.query(RunbookExecutionStep).filter_by(execution_id=execution.id).all()}


@router.post("/runbook-executions/{execution_id}/steps/{step_id}/complete")
def complete_execution_step(execution_id: UUID, step_id: UUID, payload: StepCompleteWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    execution = db.get(RunbookExecution, execution_id)
    if not execution: raise HTTPException(404, "Execution not found")
    require_property(db, user, execution.property_id); step = db.query(RunbookExecutionStep).filter_by(id=step_id, execution_id=execution.id).first()
    if not step: raise HTTPException(404, "Execution step not found")
    complete_runbook_step(db, execution, step, user.id, payload.notes, payload.evidence_reference); db.commit(); return step


@router.get("/sops")
def list_sops(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": scoped(db.query(StandardProcedure), StandardProcedure.property_id, db, user).order_by(StandardProcedure.title).all()}


@router.post("/sops", status_code=201)
def create_sop(payload: SOPWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id); row = StandardProcedure(**payload.model_dump(exclude={"slug"}), slug=payload.slug or slugify(payload.title), created_by=user.id); db.add(row); return commit_audit(db, user, "SOP_CREATED", "StandardProcedure", row, "Created standard procedure")


@router.post("/sops/{procedure_id}/sections", status_code=201)
def add_section(procedure_id: UUID, payload: SectionWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    sop = db.get(StandardProcedure, procedure_id)
    if not sop: raise HTTPException(404, "SOP not found")
    require_property(db, user, sop.property_id)
    if sop.status not in {"draft", "in_review"}: raise HTTPException(409, "Published SOP is immutable")
    row = ProcedureSection(procedure_id=sop.id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@router.post("/sops/{procedure_id}/{action}")
def sop_action(procedure_id: UUID, action: str, payload: LifecycleWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    sop = db.get(StandardProcedure, procedure_id)
    if not sop: raise HTTPException(404, "SOP not found")
    require_property(db, user, sop.property_id); targets = {"submit-review": "in_review", "approve": "approved", "publish": "published", "archive": "archived"}
    if action not in targets: raise HTTPException(404, "Unsupported SOP action")
    if action in {"approve", "publish", "archive"} and user.role not in {"admin", "superadmin"}: raise HTTPException(403, "Publisher permission required")
    if action == "submit-review": db.add(ProcedureReview(procedure_id=sop.id, reviewer_id=user.id, status="pending", notes=payload.comments))
    if action == "approve":
        review = db.query(ProcedureReview).filter_by(procedure_id=sop.id, status="pending").first()
        if not review: raise HTTPException(409, "No pending review")
        review.status, review.completed_at = "approved", datetime.now(timezone.utc)
    sop.status = targets[action]; return commit_audit(db, user, f"SOP_{action.upper().replace('-', '_')}", "StandardProcedure", sop, payload.comments or action)


@router.post("/sops/{procedure_id}/acknowledge")
def acknowledge_sop(procedure_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    sop = db.get(StandardProcedure, procedure_id)
    if not sop or sop.status != "published": raise HTTPException(409, "Published SOP required")
    require_property(db, user, sop.property_id); existing = db.query(ProcedureAcknowledgement).filter_by(procedure_id=sop.id, user_id=user.id, version=sop.version).first()
    if existing: return existing
    row = ProcedureAcknowledgement(procedure_id=sop.id, user_id=user.id, version=sop.version); db.add(row); db.commit(); db.refresh(row); return row


@router.get("/service-catalogs")
def catalogs(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": scoped(db.query(ServiceCatalog), ServiceCatalog.property_id, db, user).all()}


@router.post("/service-catalogs", status_code=201)
def create_catalog(payload: NamedWrite, db: Session = Depends(get_db), user=Depends(publisher)):
    require_property(db, user, payload.property_id); row = ServiceCatalog(property_id=payload.property_id, name=payload.name, description=payload.description); db.add(row); return commit_audit(db, user, "SERVICE_CATALOG_CREATED", "ServiceCatalog", row, "Created service catalog")


@router.get("/service-catalogs/{catalog_id}/items")
def catalog_items(catalog_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    catalog = db.get(ServiceCatalog, catalog_id)
    if not catalog: raise HTTPException(404, "Catalog not found")
    require_property(db, user, catalog.property_id); return {"items": db.query(CatalogItem).filter_by(catalog_id=catalog.id).order_by(CatalogItem.name).all()}


@router.post("/service-catalogs/{catalog_id}/items", status_code=201)
def create_catalog_item(catalog_id: UUID, payload: CatalogItemWrite, db: Session = Depends(get_db), user=Depends(publisher)):
    catalog = db.get(ServiceCatalog, catalog_id)
    if not catalog: raise HTTPException(404, "Catalog not found")
    require_property(db, user, payload.property_id or catalog.property_id); row = CatalogItem(catalog_id=catalog.id, **payload.model_dump(exclude={"slug"}), slug=payload.slug or slugify(payload.name)); db.add(row); return commit_audit(db, user, "CATALOG_ITEM_CREATED", "CatalogItem", row, "Created service catalog item")


@router.post("/catalog-items/{item_id}/dependencies", status_code=201)
def add_service_dependency(item_id: UUID, depends_on_service_id: UUID, dependency_type: str = "required", db: Session = Depends(get_db), user=Depends(publisher)):
    item = db.get(CatalogItem, item_id); dependency = db.get(CatalogItem, depends_on_service_id)
    if not item or not dependency: raise HTTPException(404, "Catalog item not found")
    require_property(db, user, item.property_id)
    if item.id == dependency.id: raise HTTPException(422, "Service cannot depend on itself")
    row = ServiceDependency(service_id=item.id, depends_on_service_id=dependency.id, dependency_type=dependency_type); db.add(row); db.commit(); db.refresh(row); return row


@router.get("/documents")
def documents(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": scoped(db.query(Document), Document.property_id, db, user).order_by(desc(Document.updated_at)).all()}


@router.post("/documents", status_code=201)
def create_document(payload: DocumentWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id); row = Document(**payload.model_dump(exclude={"slug"}), slug=payload.slug or slugify(payload.title), created_by=user.id); db.add(row); return commit_audit(db, user, "DOCUMENT_CREATED", "Document", row, "Created document record")


@router.post("/documents/{document_id}/versions", status_code=201)
def add_document_version(document_id: UUID, payload: AttachmentWrite, change_summary: str | None = None, db: Session = Depends(get_db), user=Depends(contributor)):
    document = db.get(Document, document_id)
    if not document: raise HTTPException(404, "Document not found")
    require_property(db, user, document.property_id); version = document.current_version + (1 if db.query(DocumentVersion).filter_by(document_id=document.id).count() else 0); row = DocumentVersion(document_id=document.id, version=version, change_summary=change_summary, created_by=user.id, **payload.model_dump()); document.current_version = version; db.add(row); return commit_audit(db, user, "DOCUMENT_VERSION_ADDED", "DocumentVersion", row, f"Added document version {version}")


@router.get("/documents/{document_id}/versions")
def document_versions(document_id: UUID, db: Session = Depends(get_db), user=Depends(reader)):
    document = db.get(Document, document_id)
    if not document: raise HTTPException(404, "Document not found")
    require_property(db, user, document.property_id); return {"items": db.query(DocumentVersion).filter_by(document_id=document.id).order_by(desc(DocumentVersion.version)).all()}


@router.get("/troubleshooting")
def guides(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": scoped(db.query(TroubleshootingGuide), TroubleshootingGuide.property_id, db, user).order_by(TroubleshootingGuide.title).all()}


@router.post("/troubleshooting", status_code=201)
def create_guide(payload: GuideWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id); row = TroubleshootingGuide(**payload.model_dump(exclude={"slug"}), slug=payload.slug or slugify(payload.title), created_by=user.id); db.add(row); return commit_audit(db, user, "TROUBLESHOOTING_GUIDE_CREATED", "TroubleshootingGuide", row, "Created troubleshooting guide")


@router.post("/troubleshooting/{guide_id}/symptoms", status_code=201)
def add_symptom(guide_id: UUID, symptom: str = Query(min_length=2, max_length=5000), db: Session = Depends(get_db), user=Depends(contributor)):
    guide = db.get(TroubleshootingGuide, guide_id)
    if not guide: raise HTTPException(404, "Guide not found")
    require_property(db, user, guide.property_id); row = ProblemSignature(guide_id=guide.id, symptom=symptom); db.add(row); db.commit(); db.refresh(row); return row


@router.post("/troubleshooting/{guide_id}/steps", status_code=201)
def add_resolution_step(guide_id: UUID, payload: SectionWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    guide = db.get(TroubleshootingGuide, guide_id)
    if not guide: raise HTTPException(404, "Guide not found")
    require_property(db, user, guide.property_id); row = ResolutionStep(guide_id=guide.id, sequence_order=payload.sequence_order, title=payload.heading, instructions=payload.body); db.add(row); db.commit(); db.refresh(row); return row


@router.get("/checklists")
def checklists(db: Session = Depends(get_db), user=Depends(reader)):
    return {"items": scoped(db.query(OperationalChecklistTemplate), OperationalChecklistTemplate.property_id, db, user).order_by(OperationalChecklistTemplate.name).all()}


@router.post("/checklists", status_code=201)
def create_checklist(payload: ChecklistWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id); row = OperationalChecklistTemplate(**payload.model_dump(), created_by=user.id); db.add(row); return commit_audit(db, user, "CHECKLIST_CREATED", "OperationalChecklistTemplate", row, "Created operational checklist")


@router.post("/checklists/{template_id}/items", status_code=201)
def add_checklist_item(template_id: UUID, payload: ChecklistItemWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    template = db.get(OperationalChecklistTemplate, template_id)
    if not template: raise HTTPException(404, "Checklist not found")
    require_property(db, user, template.property_id)
    if template.status not in {"draft", "in_review"}: raise HTTPException(409, "Published checklist is immutable")
    row = OperationalChecklistItem(template_id=template.id, **payload.model_dump()); db.add(row); db.commit(); db.refresh(row); return row


@router.post("/checklists/{template_id}/execute", status_code=201)
def execute_checklist(template_id: UUID, db: Session = Depends(get_db), user=Depends(contributor)):
    template = db.get(OperationalChecklistTemplate, template_id)
    if not template: raise HTTPException(404, "Checklist not found")
    require_property(db, user, template.property_id); execution = OperationalChecklistExecution(template_id=template.id, property_id=template.property_id, started_by=user.id); db.add(execution); db.flush()
    for item in db.query(OperationalChecklistItem).filter_by(template_id=template.id).order_by(OperationalChecklistItem.sequence_order): db.add(OperationalChecklistExecutionItem(execution_id=execution.id, template_item_id=item.id))
    db.commit(); db.refresh(execution); return execution


@router.post("/checklist-executions/{execution_id}/items/{item_id}/complete")
def complete_checklist_item(execution_id: UUID, item_id: UUID, outcome: str = Query(pattern=r"^(pass|fail|not_applicable)$"), evidence_reference: str | None = None, comments: str | None = None, db: Session = Depends(get_db), user=Depends(contributor)):
    execution = db.get(OperationalChecklistExecution, execution_id)
    if not execution: raise HTTPException(404, "Checklist execution not found")
    require_property(db, user, execution.property_id); item = db.query(OperationalChecklistExecutionItem).filter_by(id=item_id, execution_id=execution.id).first()
    if not item: raise HTTPException(404, "Checklist item not found")
    definition = db.get(OperationalChecklistItem, item.template_item_id)
    if definition.evidence_required and not evidence_reference: raise HTTPException(409, "Evidence required")
    item.status, item.evidence_reference, item.comments, item.completed_by, item.completed_at = outcome, evidence_reference, comments, user.id, datetime.now(timezone.utc)
    pending = db.query(OperationalChecklistExecutionItem).filter(OperationalChecklistExecutionItem.execution_id == execution.id, OperationalChecklistExecutionItem.status == "pending", OperationalChecklistExecutionItem.id != item.id).count()
    if not pending: execution.status, execution.outcome, execution.completed_at = "completed", "fail" if db.query(OperationalChecklistExecutionItem).filter_by(execution_id=execution.id, status="fail").count() or outcome == "fail" else "pass", datetime.now(timezone.utc)
    db.commit(); return item


# Safe management endpoints archive/disable records with operational history.
@router.patch("/categories/{entity_id}")
def update_category(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(publisher)):
    return update_managed(db, user, KnowledgeCategory, entity_id, payload, "KnowledgeCategory")


@router.delete("/categories/{entity_id}", status_code=204)
def delete_category(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    if db.query(KnowledgeArticle).filter_by(category_id=entity_id).first(): raise HTTPException(409, "Category is used by an article")
    return retire_managed(db, user, KnowledgeCategory, entity_id, "KnowledgeCategory")


@router.patch("/tags/{entity_id}")
def update_tag(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(publisher)):
    return update_managed(db, user, KnowledgeTag, entity_id, payload, "KnowledgeTag")


@router.delete("/tags/{entity_id}", status_code=204)
def delete_tag(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    if db.query(KnowledgeArticleTag).filter_by(tag_id=entity_id).first(): raise HTTPException(409, "Tag is used by an article")
    return retire_managed(db, user, KnowledgeTag, entity_id, "KnowledgeTag")


@router.patch("/runbooks/{entity_id}")
def update_runbook(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(contributor)):
    return update_managed(db, user, Runbook, entity_id, payload, "Runbook")


@router.delete("/runbooks/{entity_id}", status_code=204)
def archive_runbook(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    return retire_managed(db, user, Runbook, entity_id, "Runbook")


@router.patch("/sops/{entity_id}")
def update_sop(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(contributor)):
    return update_managed(db, user, StandardProcedure, entity_id, payload, "StandardProcedure")


@router.delete("/sops/{entity_id}", status_code=204)
def archive_sop(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    return retire_managed(db, user, StandardProcedure, entity_id, "StandardProcedure")


@router.patch("/service-catalogs/{entity_id}")
def update_catalog(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(publisher)):
    return update_managed(db, user, ServiceCatalog, entity_id, payload, "ServiceCatalog")


@router.delete("/service-catalogs/{entity_id}", status_code=204)
def archive_catalog(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    return retire_managed(db, user, ServiceCatalog, entity_id, "ServiceCatalog")


@router.patch("/catalog-items/{entity_id}")
def update_catalog_item(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(publisher)):
    return update_managed(db, user, CatalogItem, entity_id, payload, "CatalogItem")


@router.delete("/catalog-items/{entity_id}", status_code=204)
def archive_catalog_item(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    return retire_managed(db, user, CatalogItem, entity_id, "CatalogItem")


@router.patch("/documents/{entity_id}")
def update_document(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(contributor)):
    return update_managed(db, user, Document, entity_id, payload, "Document")


@router.delete("/documents/{entity_id}", status_code=204)
def archive_document(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    return retire_managed(db, user, Document, entity_id, "Document")


@router.patch("/troubleshooting/{entity_id}")
def update_guide(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(contributor)):
    return update_managed(db, user, TroubleshootingGuide, entity_id, payload, "TroubleshootingGuide")


@router.delete("/troubleshooting/{entity_id}", status_code=204)
def archive_guide(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    return retire_managed(db, user, TroubleshootingGuide, entity_id, "TroubleshootingGuide")


@router.patch("/checklists/{entity_id}")
def update_checklist(entity_id: UUID, payload: ManagementPatch, db: Session = Depends(get_db), user=Depends(contributor)):
    return update_managed(db, user, OperationalChecklistTemplate, entity_id, payload, "OperationalChecklistTemplate")


@router.delete("/checklists/{entity_id}", status_code=204)
def archive_checklist(entity_id: UUID, db: Session = Depends(get_db), user=Depends(publisher)):
    return retire_managed(db, user, OperationalChecklistTemplate, entity_id, "OperationalChecklistTemplate")


@router.get("/relationships")
def relationships(source_type: str | None = None, source_id: UUID | None = None, db: Session = Depends(get_db), user=Depends(reader)):
    query = scoped(db.query(KnowledgeRelationship), KnowledgeRelationship.property_id, db, user)
    if source_type: query = query.filter_by(source_type=source_type)
    if source_id: query = query.filter_by(source_id=source_id)
    return {"items": query.limit(500).all()}


@router.post("/relationships", status_code=201)
def create_relationship(payload: RelationshipWrite, db: Session = Depends(get_db), user=Depends(contributor)):
    require_property(db, user, payload.property_id)
    allowed = {"article", "runbook", "sop", "service", "device", "incident", "problem", "change", "maintenance", "asset", "document", "vendor", "location", "ticket"}
    if payload.source_type not in allowed or payload.target_type not in allowed: raise HTTPException(422, "Unsupported relationship entity type")
    if payload.source_type == payload.target_type and payload.source_id == payload.target_id: raise HTTPException(422, "Self relationships are not allowed")
    row = KnowledgeRelationship(**payload.model_dump(), created_by=user.id); db.add(row); return commit_audit(db, user, "KNOWLEDGE_RELATIONSHIP_CREATED", "KnowledgeRelationship", row, "Linked knowledge entities")


@router.get("/search")
def search(q: str = Query("", max_length=240), property_id: UUID | None = None, department_id: UUID | None = None, category_id: UUID | None = None, tag_id: UUID | None = None, status: str | None = None, author_id: str | None = None, sort: str = Query("relevance", pattern=r"^(relevance|newest|most_viewed|highest_rated|recently_updated)$"), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user=Depends(reader)):
    if property_id: require_property(db, user, property_id)
    filters = {"property_id": property_id, "department_id": department_id, "category_id": category_id, "tag_id": tag_id, "status": status, "author_id": author_id, "user_id": user.id}
    result = search_knowledge(db, q, allowed_properties(db, user), filters, page, page_size, sort); db.commit(); return result


@router.get("/reports/summary")
def report_summary(db: Session = Depends(get_db), user=Depends(reader)):
    articles = scoped(db.query(KnowledgeArticle), KnowledgeArticle.property_id, db, user); now = datetime.now(timezone.utc)
    return {"most_viewed": articles.filter_by(status="published").order_by(desc(KnowledgeArticle.view_count)).limit(10).all(), "unused_count": articles.filter(KnowledgeArticle.view_count == 0).count(), "outdated_count": articles.filter(KnowledgeArticle.next_review_at < now).count(), "approval_backlog": articles.filter_by(status="in_review").count(), "runbook_usage": scoped(db.query(RunbookExecution), RunbookExecution.property_id, db, user).count(), "sop_acknowledgements": db.query(ProcedureAcknowledgement).count(), "searches": db.query(KnowledgeSearchStat).count(), "health_score": max(0, 100 - min(100, articles.filter(KnowledgeArticle.next_review_at < now).count() * 5))}


@router.get("/audit-history")
def knowledge_audit_history(entity_type: str | None = Query(None, max_length=80), entity_id: str | None = Query(None, max_length=80), page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100), db: Session = Depends(get_db), user=Depends(reader)):
    knowledge_entities = {"KnowledgeArticle", "KnowledgeAttachment", "KnowledgeCategory", "KnowledgeTag", "Runbook", "RunbookVersion", "StandardProcedure", "ServiceCatalog", "CatalogItem", "Document", "DocumentVersion", "TroubleshootingGuide", "OperationalChecklistTemplate", "KnowledgeRelationship"}
    if entity_type and entity_type not in knowledge_entities: raise HTTPException(422, "Unsupported knowledge audit entity")
    query = db.query(AuditLog).filter(AuditLog.entity_type.in_(knowledge_entities))
    if entity_type: query = query.filter_by(entity_type=entity_type)
    if entity_id: query = query.filter_by(entity_id=entity_id)
    total = query.count(); items = query.order_by(desc(AuditLog.created_at)).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/reports/export")
def export_report(format: str = Query("csv", pattern=r"^(csv|xlsx|pdf)$"), db: Session = Depends(get_db), user=Depends(reader)):
    rows = scoped(db.query(KnowledgeArticle), KnowledgeArticle.property_id, db, user).order_by(KnowledgeArticle.title).limit(5000).all()
    safe = lambda value: f"'{value}" if str(value or "").startswith(("=", "+", "-", "@")) else str(value or "")
    if format == "csv":
        stream = io.StringIO(); writer = csv.writer(stream); writer.writerow(["Title", "Status", "Version", "Views", "Rating", "Updated"])
        for row in rows: writer.writerow([safe(row.title), row.status, row.version, row.view_count, row.rating_average, row.updated_at.isoformat()])
        return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=knowledge-report.csv"})
    if format == "xlsx":
        workbook = Workbook(); sheet = workbook.active; sheet.title = "Knowledge"; sheet.append(["Title", "Status", "Version", "Views", "Rating", "Updated"])
        for row in rows: sheet.append([safe(row.title), row.status, row.version, row.view_count, row.rating_average, row.updated_at.isoformat()])
        output = io.BytesIO(); workbook.save(output); return Response(output.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": "attachment; filename=knowledge-report.xlsx"})
    content = printable_pdf("HIOP Knowledge Report", [f"{index + 1}. {safe(row.title)} | {row.status} | views {row.view_count}" for index, row in enumerate(rows)])
    return Response(content, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=knowledge-report.pdf"})
