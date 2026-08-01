import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import desc, func, or_

from app.models.knowledge import (
    Document, KnowledgeApproval, KnowledgeArticle, KnowledgeArticleTag,
    KnowledgeFavorite, KnowledgeRating, KnowledgeRevision, KnowledgeSearchStat,
    KnowledgeTag, KnowledgeViewHistory, Runbook, RunbookExecution,
    RunbookExecutionStep, RunbookStep, RunbookVersion, StandardProcedure,
    TroubleshootingGuide,
)
from app.services.audit_service import create_audit_log
from app.websocket.connection_manager import manager

ARTICLE_TRANSITIONS = {
    "draft": {"in_review"}, "in_review": {"draft", "approved"},
    "approved": {"published", "draft"}, "published": {"archived"},
    "archived": {"draft"},
}
UNSAFE_MARKDOWN = re.compile(r"<\s*(script|iframe|object|embed)|javascript\s*:", re.I)
SLUG = re.compile(r"[^a-z0-9]+")


def safe_markdown(value: str, maximum=200_000) -> str:
    if len(value.encode("utf-8")) > maximum:
        raise HTTPException(422, "Markdown content exceeds the size limit")
    if UNSAFE_MARKDOWN.search(value):
        raise HTTPException(422, "Executable or embedded markup is not permitted")
    return value


def slugify(value: str) -> str:
    slug = SLUG.sub("-", value.lower()).strip("-")
    if not slug:
        raise HTTPException(422, "A valid title is required")
    return slug[:240]


def checksum(*values) -> str:
    return hashlib.sha256("\n".join(str(value or "") for value in values).encode()).hexdigest()


def snapshot_article(db, article, actor, change_summary):
    existing = db.query(KnowledgeRevision).filter_by(article_id=article.id, version=article.version).first()
    if existing:
        return existing
    row = KnowledgeRevision(
        article_id=article.id, version=article.version, title=article.title,
        summary=article.summary, body=article.body, change_summary=change_summary,
        checksum_sha256=checksum(article.title, article.summary, article.body),
        created_by=actor,
    )
    db.add(row)
    db.flush()
    return row


def transition_article(db, article, target, actor, comments=None):
    if target not in ARTICLE_TRANSITIONS.get(article.status, set()):
        raise HTTPException(409, f"Cannot transition article from {article.status} to {target}")
    now = datetime.now(timezone.utc)
    if target == "in_review":
        revision = snapshot_article(db, article, actor, comments or "Submitted for review")
        article.approval_state = "pending"
        db.add(KnowledgeApproval(
            article_id=article.id, revision_id=revision.id, status="pending",
            comments=comments, requested_by=actor,
        ))
    elif target == "approved":
        approval = db.query(KnowledgeApproval).filter_by(article_id=article.id, status="pending").order_by(desc(KnowledgeApproval.requested_at)).first()
        if not approval:
            raise HTTPException(409, "No pending approval exists")
        approval.status, approval.reviewer_id, approval.comments, approval.decided_at = "approved", actor, comments, now
        article.approval_state = "approved"
    elif target == "published":
        if article.approval_state != "approved":
            raise HTTPException(409, "Only an approved article may be published")
        article.published_at = now
    elif target == "archived":
        article.archived_at = now
    elif target == "draft":
        article.version += 1
        article.approval_state = "not_submitted"
        article.published_at = article.archived_at = None
    article.status = target
    article.updated_at = now
    create_audit_log(db, actor, f"KNOWLEDGE_ARTICLE_{target.upper()}", "KnowledgeArticle", str(article.id), comments or f"Article moved to {target}")
    manager.broadcast_from_thread({"type": "knowledge_article_updated", "article_id": str(article.id), "property_id": str(article.property_id) if article.property_id else None, "status": target})
    return article


def rollback_article(db, article, revision, actor):
    if article.status in {"published", "approved"}:
        raise HTTPException(409, "Return the article to draft before rollback")
    snapshot_article(db, article, actor, f"Before rollback to version {revision.version}")
    article.version += 1
    article.title, article.summary, article.body = revision.title, revision.summary, revision.body
    article.approval_state, article.status = "not_submitted", "draft"
    create_audit_log(db, actor, "KNOWLEDGE_ARTICLE_ROLLED_BACK", "KnowledgeArticle", str(article.id), f"Restored revision {revision.version} into version {article.version}")
    return article


def rate_article(db, article, user_id, rating, feedback=None):
    row = db.query(KnowledgeRating).filter_by(article_id=article.id, user_id=user_id).first()
    if row:
        row.rating, row.feedback = rating, feedback
    else:
        row = KnowledgeRating(article_id=article.id, user_id=user_id, rating=rating, feedback=feedback)
        db.add(row)
    db.flush()
    average, count = db.query(func.avg(KnowledgeRating.rating), func.count(KnowledgeRating.id)).filter_by(article_id=article.id).one()
    article.rating_average, article.rating_count = float(average or 0), count
    return row


def record_view(db, article, user_id):
    article.view_count += 1
    db.add(KnowledgeViewHistory(article_id=article.id, user_id=user_id))


def search_knowledge(db, query, allowed_properties, filters, page, page_size, sort):
    query = query.strip()[:240]
    article_query = db.query(KnowledgeArticle).filter(KnowledgeArticle.status == "published")
    if allowed_properties is not None:
        article_query = article_query.filter(or_(KnowledgeArticle.property_id.is_(None), KnowledgeArticle.property_id.in_(allowed_properties)))
    if query:
        pattern = f"%{query}%"
        article_query = article_query.filter(or_(KnowledgeArticle.title.ilike(pattern), KnowledgeArticle.summary.ilike(pattern), KnowledgeArticle.body.ilike(pattern)))
    for key, column in (("property_id", KnowledgeArticle.property_id), ("department_id", KnowledgeArticle.department_id), ("category_id", KnowledgeArticle.category_id), ("status", KnowledgeArticle.status), ("author_id", KnowledgeArticle.author_id)):
        if filters.get(key):
            article_query = article_query.filter(column == filters[key])
    if filters.get("tag_id"):
        article_query = article_query.join(KnowledgeArticleTag).filter(KnowledgeArticleTag.tag_id == filters["tag_id"])
    order = {
        "newest": KnowledgeArticle.published_at.desc(),
        "most_viewed": KnowledgeArticle.view_count.desc(),
        "highest_rated": KnowledgeArticle.rating_average.desc(),
        "recently_updated": KnowledgeArticle.updated_at.desc(),
    }.get(sort, KnowledgeArticle.updated_at.desc())
    total = article_query.count()
    articles = article_query.order_by(order).offset((page - 1) * page_size).limit(page_size).all()

    def simple(model, entity_type, title_column, summary_column=None):
        q = db.query(model)
        property_column = getattr(model, "property_id", None)
        if allowed_properties is not None and property_column is not None:
            q = q.filter(or_(property_column.is_(None), property_column.in_(allowed_properties)))
        if query:
            clauses = [title_column.ilike(f"%{query}%")]
            if summary_column is not None:
                clauses.append(summary_column.ilike(f"%{query}%"))
            q = q.filter(or_(*clauses))
        rows = q.limit(min(25, page_size)).all()
        return [{"entity_type": entity_type, "id": str(row.id), "title": getattr(row, "title", getattr(row, "name", "")), "summary": getattr(row, "summary", getattr(row, "objective", None)), "status": row.status} for row in rows]

    results = [{"entity_type": "article", "id": str(row.id), "title": row.title, "summary": row.summary, "status": row.status, "score": 1.0} for row in articles]
    if page == 1:
        results += simple(Runbook, "runbook", Runbook.name, Runbook.objective)
        results += simple(StandardProcedure, "sop", StandardProcedure.title, StandardProcedure.summary)
        results += simple(Document, "document", Document.title, Document.summary)
        results += simple(TroubleshootingGuide, "troubleshooting", TroubleshootingGuide.title, TroubleshootingGuide.summary)
    db.add(KnowledgeSearchStat(property_id=filters.get("property_id"), user_id=filters.get("user_id"), query_text=query or "*", filters=json.dumps({key: str(value) for key, value in filters.items() if value and key != "user_id"}), result_count=len(results)))
    return {"items": results, "total": total + max(0, len(results) - len(articles)), "page": page, "page_size": page_size, "query": query, "sort": sort}


def start_runbook(db, runbook, version, actor, property_id, parameters, links):
    if version.status != "approved" or runbook.current_version_id != version.id:
        raise HTTPException(409, "Runbook execution requires the active approved version")
    execution = RunbookExecution(
        runbook_id=runbook.id, version_id=version.id, property_id=property_id,
        parameters=json.dumps(parameters, separators=(",", ":")), started_by=actor,
        incident_id=links.get("incident_id"), ticket_id=links.get("ticket_id"),
        workflow_run_id=links.get("workflow_run_id"),
    )
    db.add(execution)
    db.flush()
    steps = db.query(RunbookStep).filter_by(version_id=version.id).order_by(RunbookStep.sequence_order).all()
    for index, step in enumerate(steps):
        db.add(RunbookExecutionStep(execution_id=execution.id, runbook_step_id=step.id, step_key=step.step_key, status="ready" if index == 0 else "pending"))
    create_audit_log(db, actor, "RUNBOOK_EXECUTION_STARTED", "RunbookExecution", str(execution.id), f"Started approved runbook {runbook.name}")
    return execution


def complete_runbook_step(db, execution, step_run, actor, notes, evidence_reference):
    if execution.status != "running" or step_run.status != "ready":
        raise HTTPException(409, "Runbook step is not ready")
    definition = db.get(RunbookStep, step_run.runbook_step_id)
    if definition.evidence_required and not evidence_reference:
        raise HTTPException(409, "Evidence is required for this step")
    step_run.status, step_run.notes, step_run.evidence_reference = "completed", notes, evidence_reference
    step_run.completed_by, step_run.completed_at = actor, datetime.now(timezone.utc)
    next_step = db.query(RunbookExecutionStep).join(RunbookStep).filter(
        RunbookExecutionStep.execution_id == execution.id,
        RunbookExecutionStep.status == "pending",
    ).order_by(RunbookStep.sequence_order).first()
    if next_step:
        next_step.status = "ready"
    else:
        execution.status, execution.completed_at = "completed", datetime.now(timezone.utc)
    return step_run


def publish_and_archive_due(db, now_value=None):
    now_value = now_value or datetime.now(timezone.utc)
    published = db.query(KnowledgeArticle).filter(KnowledgeArticle.status == "approved", KnowledgeArticle.publish_at <= now_value).limit(500).all()
    archived = db.query(KnowledgeArticle).filter(KnowledgeArticle.status == "published", KnowledgeArticle.archive_at <= now_value).limit(500).all()
    for article in published:
        transition_article(db, article, "published", "scheduler", "Scheduled publishing")
    for article in archived:
        transition_article(db, article, "archived", "scheduler", "Scheduled archiving")
    return {"published": len(published), "archived": len(archived)}
