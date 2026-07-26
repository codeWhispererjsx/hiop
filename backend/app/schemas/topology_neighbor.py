"""Bounded request and response contracts for neighbor discovery."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NeighborCollectionRequest(BaseModel):
    target_ids: list[UUID] = Field(min_length=1, max_length=100)
    protocol_mode: Literal["auto", "lldp", "cdp", "both"] = "auto"
    dry_run: bool = False

    @model_validator(mode="after")
    def unique_targets(self):
        if len(set(self.target_ids)) != len(self.target_ids):
            raise ValueError("Target IDs must be unique.")
        return self


class PerTargetCollectionRequest(BaseModel):
    protocol_mode: Literal["auto", "lldp", "cdp", "both"] = "auto"
    dry_run: bool = False


class CandidateMatchRequest(BaseModel):
    topology_node_id: UUID | None = None
    device_id: UUID | None = None
    discovered_device_id: UUID | None = None
    snmp_target_id: UUID | None = None

    @model_validator(mode="after")
    def one_match(self):
        if sum(value is not None for value in (
            self.topology_node_id, self.device_id, self.discovered_device_id, self.snmp_target_id
        )) != 1:
            raise ValueError("Select exactly one candidate match.")
        return self


class NeighborRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    target_id: UUID
    started_at: datetime
    completed_at: datetime | None
    status: str
    protocols_requested: list[str]
    protocols_completed: list[str]
    local_ports_seen: int
    raw_neighbors_seen: int
    normalized_neighbors: int
    candidate_nodes_created: int
    candidate_links_created: int
    candidate_links_updated: int
    conflicts: int
    errors_count: int
    trigger_type: str
    duration_ms: int | None
    error_category: str | None
    error_summary: str | None
    dry_run: bool


class NeighborObservationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    collection_run_id: UUID
    topology_id: UUID
    source_target_id: UUID
    source_node_id: UUID | None
    source_interface_id: UUID | None
    protocol: str
    local_port_identifier: str
    local_port_description: str | None
    remote_identity_key: str
    remote_chassis_id: str | None
    remote_port_id: str | None
    remote_system_name: str | None
    remote_management_address: str | None
    remote_capabilities: list[str]
    remote_platform: str | None
    native_vlan: int | None
    duplex: str | None
    first_seen_at: datetime
    last_seen_at: datetime
    observation_status: str
    missing_collections: int
    normalized_identity: dict[str, Any]


class NeighborCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    source_observation_id: UUID | None
    remote_identity_key: str
    remote_chassis_id: str | None
    remote_system_name: str | None
    remote_management_address: str | None
    remote_port_id: str | None
    vendor_guess: str | None
    device_type_guess: str
    matched_device_id: UUID | None
    matched_discovered_device_id: UUID | None
    matched_snmp_target_id: UUID | None
    matched_topology_node_id: UUID | None
    confidence_score: int
    score_breakdown: dict[str, Any]
    evidence: dict[str, Any]
    conflict_flags: list[str]
    review_status: str
    created_at: datetime
    updated_at: datetime
