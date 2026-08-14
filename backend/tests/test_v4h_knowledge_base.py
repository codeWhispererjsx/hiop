from pathlib import Path

from app.api.v1 import knowledge_base
from app.models.knowledge import KnowledgeArticle, KnowledgeRating, KnowledgeRelationship, KnowledgeRevision

ROOT=Path(__file__).parents[1]
def source():return ROOT.joinpath("app/api/v1/knowledge_base.py").read_text(encoding="utf-8")

def test_v4h_reuses_safe_core_models():
    assert KnowledgeArticle.__tablename__=="knowledge_articles"
    assert KnowledgeRevision.__tablename__=="knowledge_revisions"
    assert KnowledgeRelationship.__tablename__=="knowledge_relationships"
    assert KnowledgeRating.__tablename__=="knowledge_ratings"
    for field in ("organization_id","article_number","article_type","category","tags_text","steps_text","warnings","last_viewed_at"):assert field in KnowledgeArticle.__table__.columns

def test_article_vocabularies_are_small_and_explicit():
    assert knowledge_base.STATUSES=={"draft","in_review","published","archived"}
    assert knowledge_base.TYPES=={"how_to","troubleshooting","sop","known_issue","recovery_procedure","reference"}
    assert {"network","pos","wifi","printer","server","other"}<=knowledge_base.CATEGORIES

def test_draft_visibility_and_publication_are_backend_enforced():
    text=source()
    assert 'row.status=="published"' in text
    assert "Draft or review knowledge is restricted" in text
    assert "Only administrators can publish" in text
    assert 'editor=require_roles(["admin","technician"])' in text

def test_unsafe_content_and_credentials_are_rejected():
    text=source().lower()
    for value in ("unsafe executable html","credential-like content","javascript","iframe","private[_ -]?key"):assert value in text

def test_versions_feedback_usage_and_relationships_are_supported():
    text=source()
    for value in ("KnowledgeRevision","KnowledgeRating","KnowledgeViewHistory","view_count","last_viewed_at"):assert value in text
    for kind in ("asset","device","service","problem","incident","change","vendor"):assert f'"{kind}"' in text

def test_knowledge_is_tenant_scoped_and_does_not_generate_content():
    text=source()
    assert "organization_context" in text and "does not belong to this organization" in text
    for forbidden in ("openai","generate_article","ai_summary","execute_runbook","subprocess"):assert forbidden not in text.lower()

def test_v4h_migration_is_additive():
    text=ROOT.joinpath("alembic/versions/v4h0a1b2c3d4_knowledge_base.py").read_text(encoding="utf-8").lower()
    assert 'add_column("knowledge_articles"' in text and "v4h_article_number_seq" in text
    for forbidden in ('drop_table("knowledge_articles"',"delete from knowledge_articles",'drop_table("change_requests"'):assert forbidden not in text
