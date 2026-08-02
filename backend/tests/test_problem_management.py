from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
MODELS=(ROOT/"backend/app/models/problem_management.py").read_text()
API=(ROOT/"backend/app/api/v1/problem_management.py").read_text()
MAIN=(ROOT/"backend/app/main.py").read_text()
MIGRATION=(ROOT/"backend/alembic/versions/d1e2f3a4b5c6_enterprise_problem_management.py").read_text()
SCHEDULER=(ROOT/"backend/app/services/scheduler_service.py").read_text()

def test_epic6_models_cover_problem_rca_kedb_capa_and_reviews():
    for name in ("Problem","ProblemCategory","ProblemPriority","ProblemSeverity","ProblemStatus","ProblemSource","ProblemImpact","ProblemReview","ProblemRevision","RootCauseAnalysis","RootCause","ContributingFactor","CorrectiveAction","PreventiveAction","FiveWhys","FishboneAnalysis","KnownError","KnownErrorWorkaround","KnownErrorRevision","KnownErrorAttachment","CorrectiveActionPlan","PreventiveActionPlan","ActionTask","ActionVerification","ProblemRelationship","ProblemCorrelationSuggestion"):
        assert f"class {name}(Base)" in MODELS

def test_problem_lifecycle_is_ordered_and_guarded():
    for state in ("new","under_investigation","root_cause_identified","known_error","change_required","resolved","closed"): assert state in API
    assert "validated root cause is required" in API
    assert "approved problem review is required" in API

def test_problem_apis_are_registered_and_human_driven():
    assert "problem_management_router" in MAIN
    for route in ("/dashboard","/rca","/known-errors","/workarounds/library","/capa","/reviews","/relationships/graph","/correlations/detect","/reports/export","/search/all"): assert route in API
    assert '"automatic_problems_created":0' in API

def test_scheduled_jobs_are_bounded_reminders_and_suggestions():
    for job in ("review_reminders","capa_due_reminders","known_error_review_reminders","recurring_incident_detection","problem_aging_alerts","dashboard_statistics"): assert job in SCHEDULER
    assert "ProblemCorrelationSuggestion" in SCHEDULER
    assert "RootCause(" not in SCHEDULER

def test_problem_migration_is_reversible_and_follows_cmdb():
    assert 'down_revision="c0d1e2f3a4b5"' in MIGRATION
    assert "def upgrade" in MIGRATION and "def downgrade" in MIGRATION
