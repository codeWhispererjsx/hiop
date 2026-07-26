"""Strict, bounded topology API schemas."""
import ipaddress
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TopologyWrite(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    topology_type: Literal["physical", "logical", "dependency", "network", "floor", "building", "custom"] = "physical"
    scope_type: Literal["global", "building", "floor", "department", "network_zone", "custom"] = "global"
    building_id: UUID | None = None
    floor_id: UUID | None = None
    department_id: UUID | None = None
    network_zone_id: UUID | None = None
    enabled: bool = True
    is_default: bool = False
    layout_mode: Literal["manual", "hierarchical", "force", "grid"] = "manual"


class TopologyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    layout_mode: Literal["manual", "hierarchical", "force", "grid"] | None = None


class TopologyRead(TopologyWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    root_node_id: UUID | None
    created_at: datetime
    updated_at: datetime


class NodeWrite(BaseModel):
    device_id: UUID | None = None
    discovered_device_id: UUID | None = None
    snmp_target_id: UUID | None = None
    node_type: str = Field(default="unknown", max_length=40)
    label: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    status: str = Field(default="unknown", max_length=30)
    role: str = Field(default="unknown", max_length=30)
    layer: str = Field(default="unknown", max_length=30)
    parent_node_id: UUID | None = None
    network_zone_id: UUID | None = None
    building_id: UUID | None = None
    floor_id: UUID | None = None
    room_id: UUID | None = None
    department_id: UUID | None = None
    management_ip: str | None = Field(default=None, max_length=45)
    vendor: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    source_type: str = Field(default="manual", max_length=30)
    confidence_score: int = Field(default=100, ge=0, le=100)
    is_manual: bool = True
    is_hidden: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def identity(self):
        identities = sum(value is not None for value in (self.device_id, self.discovered_device_id, self.snmp_target_id))
        if identities > 1:
            raise ValueError("A topology node may reference only one authoritative/provisional identity.")
        if len(str(self.metadata)) > 8000:
            raise ValueError("Topology metadata exceeds the safe limit.")
        return self

    @field_validator("management_ip")
    @classmethod
    def ip(cls, value):
        if value:
            ipaddress.ip_address(value)
        return value


class NodeUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    status: str | None = Field(default=None, max_length=30)
    role: str | None = Field(default=None, max_length=30)
    layer: str | None = Field(default=None, max_length=30)
    parent_node_id: UUID | None = None
    is_hidden: bool | None = None


class NodeRead(NodeWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime


class LinkWrite(BaseModel):
    source_node_id: UUID
    target_node_id: UUID
    source_interface_id: UUID | None = None
    target_interface_id: UUID | None = None
    link_type: str = Field(default="physical", max_length=30)
    direction: Literal["bidirectional", "source_to_target", "target_to_source", "unknown"] = "bidirectional"
    status: Literal["active", "inactive", "degraded", "missing", "unknown"] = "active"
    speed_bps: int | None = Field(default=None, ge=0)
    duplex: str | None = Field(default=None, max_length=20)
    vlan_id: int | None = Field(default=None, ge=1, le=4094)
    lag_identifier: str | None = Field(default=None, max_length=80)
    source_type: str = Field(default="manual", max_length=30)
    confidence_score: int = Field(default=100, ge=0, le=100)
    discovery_method: Literal["manual", "LLDP", "CDP", "SNMP", "bridge_table", "MAC_table", "ARP", "subnet", "hostname_rule", "imported", "inferred", "unknown"] = "manual"
    is_manual: bool = True
    is_confirmed: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def not_self(self):
        if self.source_node_id == self.target_node_id:
            raise ValueError("Topology self-links are not permitted.")
        if len(str(self.metadata)) > 8000:
            raise ValueError("Topology metadata exceeds the safe limit.")
        return self


class LinkUpdate(BaseModel):
    status: str | None = Field(default=None, max_length=30)
    speed_bps: int | None = Field(default=None, ge=0)
    vlan_id: int | None = Field(default=None, ge=1, le=4094)
    is_confirmed: bool | None = None
    is_suppressed: bool | None = None


class LinkRead(LinkWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    is_suppressed: bool
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")
    created_at: datetime
    updated_at: datetime


class SegmentWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    cidr: str = Field(max_length=64)
    vlan_id: int | None = Field(default=None, ge=1, le=4094)
    vlan_name: str | None = Field(default=None, max_length=120)
    segment_type: str = Field(default="unknown", max_length=30)
    network_zone_id: UUID | None = None
    description: str | None = Field(default=None, max_length=500)
    enabled: bool = True
    source_type: str = "manual"
    confidence_score: int = Field(default=100, ge=0, le=100)

    @field_validator("cidr")
    @classmethod
    def cidr_valid(cls, value):
        return str(ipaddress.ip_network(value, strict=False))


class SegmentRead(SegmentWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    created_at: datetime
    updated_at: datetime


class DependencyWrite(BaseModel):
    upstream_node_id: UUID
    downstream_node_id: UUID
    dependency_type: str = Field(max_length=30)
    criticality: Literal["low", "medium", "high", "critical"] = "medium"
    source_type: str = "manual"
    confidence_score: int = Field(default=100, ge=0, le=100)
    enabled: bool = True
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def not_self(self):
        if self.upstream_node_id == self.downstream_node_id:
            raise ValueError("Self-dependencies are not permitted.")
        return self


class DependencyRead(DependencyWrite):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    topology_id: UUID
    created_at: datetime
    updated_at: datetime


class PositionWrite(BaseModel):
    node_id: UUID
    x_position: float = Field(ge=-100000, le=100000)
    y_position: float = Field(ge=-100000, le=100000)
    group_id: UUID | None = None
    locked: bool = False
    layout_version: int = Field(default=1, ge=1, le=100000)


class SnapshotWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    snapshot_type: Literal["manual", "pre_change", "post_change", "baseline"] = "manual"


class BootstrapRequest(BaseModel):
    include_snmp_managed_devices: bool = True
    include_discovered_devices: bool = False
    include_only_active_inventory: bool = True
    create_provisional_nodes: bool = False
    dry_run: bool = True
