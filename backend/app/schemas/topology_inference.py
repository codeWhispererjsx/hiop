"""Contracts for bounded, review-first topology inference."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class InferenceRequest(BaseModel):
    dry_run: bool = False
    include_dependencies: bool = True
    include_layer_suggestions: bool = True


class ReviewResolution(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class InferenceRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    dry_run: bool
    nodes_analyzed: int
    links_analyzed: int
    links_merged: int
    node_recommendations: int
    dependencies_inferred: int
    conflicts_detected: int
    review_items_created: int
    graph_checksum_before: str | None
    graph_checksum_after: str | None
    summary: dict[str, Any]
    error_summary: str | None
    duration_ms: int | None


class ConflictRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    inference_run_id: UUID | None
    conflict_type: str
    severity: str
    entity_type: str
    entity_id: UUID | None
    related_entity_ids: list[str]
    confidence_score: int
    evidence: dict[str, Any]
    suggested_resolution: str
    status: str
    detected_at: datetime


class ReviewItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    inference_run_id: UUID | None
    review_type: str
    entity_type: str
    entity_id: UUID | None
    dedupe_key: str
    proposed_change: dict[str, Any]
    evidence: dict[str, Any]
    impact: dict[str, Any]
    confidence_score: int
    status: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    resolution_note: str | None
    created_at: datetime


class PathAnalysisQuery(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    path_type: Literal["physical", "dependency", "layer_aware", "any"] = "any"
    max_depth: int = Field(default=20, ge=1, le=100)
    max_paths: int = Field(default=5, ge=1, le=20)
