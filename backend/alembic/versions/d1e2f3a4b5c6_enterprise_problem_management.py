"""Enterprise Problem Management and Known Error Database.

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
"""
from alembic import op

from app.models.problem_management import (
    ActionTask, ActionVerification, ContributingFactor, CorrectiveAction,
    CorrectiveActionPlan, FishboneAnalysis, FiveWhys, KnownError,
    KnownErrorAttachment, KnownErrorRevision, KnownErrorWorkaround,
    PreventiveAction, PreventiveActionPlan, Problem, ProblemCategory,
    ProblemCorrelationSuggestion, ProblemImpact, ProblemPriority,
    ProblemRelationship, ProblemReview, ProblemRevision, ProblemSeverity,
    ProblemSource, ProblemStatus, RootCause, RootCauseAnalysis,
)

revision="d1e2f3a4b5c6"; down_revision="c0d1e2f3a4b5"; branch_labels=None; depends_on=None

TABLES=[ProblemCategory,ProblemPriority,ProblemSeverity,ProblemStatus,ProblemSource,Problem,ProblemImpact,ProblemRevision,ProblemReview,RootCauseAnalysis,RootCause,ContributingFactor,FiveWhys,FishboneAnalysis,KnownError,KnownErrorWorkaround,KnownErrorRevision,KnownErrorAttachment,CorrectiveActionPlan,PreventiveActionPlan,CorrectiveAction,PreventiveAction,ActionTask,ActionVerification,ProblemRelationship,ProblemCorrelationSuggestion]

def upgrade():
    bind=op.get_bind()
    for model in TABLES:model.__table__.create(bind,checkfirst=True)

def downgrade():
    bind=op.get_bind()
    for model in reversed(TABLES):model.__table__.drop(bind,checkfirst=True)
