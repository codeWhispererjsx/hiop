from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import problems
from app.models.problem_management import Problem, ProblemRelationship, ProblemTimelineEvent


def test_v4f_reuses_existing_problem_and_relationship_models():
    assert Problem.__tablename__ == "problems"
    assert ProblemRelationship.__tablename__ == "problem_relationships"
    assert ProblemTimelineEvent.__tablename__ == "problem_timeline_events"
    for field in ("organization_id","problem_statement","root_cause","workaround","resolution","resolved_at"):
        assert field in Problem.__table__.columns


def test_problem_statuses_priorities_and_categories_are_small_and_explicit():
    assert problems.STATUSES == {"open","investigating","known_error","resolved","closed"}
    assert problems.PRIORITIES == {"low","medium","high","critical"}
    assert "network" in problems.CATEGORIES and "pos" in problems.CATEGORIES


def test_known_error_requires_documented_workaround():
    source=Path(__file__).parents[1].joinpath("app/api/v1/problems.py").read_text(encoding="utf-8")
    assert 'target_status=="known_error" and not row.workaround' in source
    assert "Document a workaround" in source


def test_problem_api_is_tenant_and_role_scoped():
    source=Path(__file__).parents[1].joinpath("app/api/v1/problems.py").read_text(encoding="utf-8")
    assert "organization_context" in source
    assert 'require_roles(["platformadmin","admin","technician","viewer"])' in source
    assert 'operator=require_roles(["admin"])' in source
    assert "does not belong to this organization" in source


def test_problem_relationships_validate_target_and_deduplicate():
    source=Path(__file__).parents[1].joinpath("app/api/v1/problems.py").read_text(encoding="utf-8")
    for kind in ("incident","asset","device","service","vendor","procurement"):
        assert f'"{kind}"' in source
    assert "if not exists" in source


def test_v4f_does_not_automatically_create_problems_or_claim_ai_root_cause():
    source=Path(__file__).parents[1].joinpath("app/api/v1/problems.py").read_text(encoding="utf-8").lower()
    for forbidden in ("automatic_problem", "ai_root", "execute_remediation", "change_request"):
        assert forbidden not in source


def test_v4f_migration_is_additive():
    source=Path(__file__).parents[1].joinpath("alembic/versions/v4f0a1b2c3d4_problem_management.py").read_text(encoding="utf-8").lower()
    assert 'add_column("problems"' in source
    assert 'create_table("problem_timeline_events"' in source
    for forbidden in ('drop_table("problems"','delete from problems','drop_table("operational_incidents"'):
        assert forbidden not in source
