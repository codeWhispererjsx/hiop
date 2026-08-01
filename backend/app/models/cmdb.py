import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.database import Base


def uid(): return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
def now(): return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CIClass(Base):
    __tablename__ = "ci_classes"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(100), unique=True); code: Mapped[str] = mapped_column(String(60), unique=True, index=True); domain: Mapped[str] = mapped_column(String(60), index=True); description: Mapped[str | None] = mapped_column(Text); enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CIType(Base):
    __tablename__ = "ci_types"
    id: Mapped[uuid.UUID] = uid(); class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ci_classes.id"), index=True); name: Mapped[str] = mapped_column(String(120)); code: Mapped[str] = mapped_column(String(80), unique=True, index=True); category: Mapped[str | None] = mapped_column(String(100)); attribute_schema: Mapped[str] = mapped_column(Text, default="{}"); enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true"); __table_args__ = (UniqueConstraint("class_id", "name", name="uq_ci_type_class_name"),)


class CIStatus(Base):
    __tablename__ = "ci_statuses"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(50), unique=True); code: Mapped[str] = mapped_column(String(40), unique=True); operational: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); terminal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class CILifecycle(Base):
    __tablename__ = "ci_lifecycles"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(50), unique=True); code: Mapped[str] = mapped_column(String(40), unique=True); sequence_order: Mapped[int] = mapped_column(Integer, unique=True); terminal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class ConfigurationItem(Base):
    __tablename__ = "configuration_items"
    id: Mapped[uuid.UUID] = uid(); ci_number: Mapped[str] = mapped_column(String(32), unique=True, index=True); name: Mapped[str] = mapped_column(String(180), index=True); display_name: Mapped[str | None] = mapped_column(String(220)); description: Mapped[str | None] = mapped_column(Text)
    type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ci_types.id"), index=True); class_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ci_classes.id"), index=True); category: Mapped[str | None] = mapped_column(String(100), index=True)
    owner_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); department_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("departments.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="active", server_default="active", index=True); lifecycle_stage: Mapped[str] = mapped_column(String(40), default="planned", server_default="planned", index=True); criticality: Mapped[str] = mapped_column(String(20), default="medium", server_default="medium", index=True); operational_status: Mapped[str] = mapped_column(String(40), default="unknown", server_default="unknown", index=True)
    installation_date: Mapped[date | None] = mapped_column(Date); warranty_date: Mapped[date | None] = mapped_column(Date, index=True); retirement_date: Mapped[date | None] = mapped_column(Date); manufacturer: Mapped[str | None] = mapped_column(String(160), index=True); model: Mapped[str | None] = mapped_column(String(160)); serial_number: Mapped[str | None] = mapped_column(String(180), index=True)
    asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id"), unique=True, index=True); discovered_device_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("discovered_devices.id"), unique=True); discovery_source: Mapped[str] = mapped_column(String(40), default="manual", server_default="manual", index=True); source_reference: Mapped[str | None] = mapped_column(String(180)); last_discovery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True); verification_status: Mapped[str] = mapped_column(String(30), default="unverified", server_default="unverified", index=True); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now(); updated_at: Mapped[datetime] = now()
    __table_args__ = (Index("ix_configuration_items_property_class_status", "property_id", "class_id", "status"),)


class CIAttribute(Base):
    __tablename__ = "ci_attributes"
    id: Mapped[uuid.UUID] = uid(); ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), index=True); name: Mapped[str] = mapped_column(String(100)); data_type: Mapped[str] = mapped_column(String(30)); value_text: Mapped[str | None] = mapped_column(Text); value_number: Mapped[float | None] = mapped_column(Float); value_boolean: Mapped[bool | None] = mapped_column(Boolean); unit: Mapped[str | None] = mapped_column(String(40)); source: Mapped[str] = mapped_column(String(40), default="manual"); verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); updated_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); updated_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("ci_id", "name", name="uq_ci_attribute_name"),)


class CIAttributeHistory(Base):
    __tablename__ = "ci_attribute_history"
    id: Mapped[uuid.UUID] = uid(); attribute_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ci_attributes.id", ondelete="CASCADE"), index=True); previous_value: Mapped[str | None] = mapped_column(Text); current_value: Mapped[str | None] = mapped_column(Text); changed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); reason: Mapped[str | None] = mapped_column(String(500)); changed_at: Mapped[datetime] = now()


class CIIdentifier(Base):
    __tablename__ = "ci_identifiers"
    id: Mapped[uuid.UUID] = uid(); ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), index=True); identifier_type: Mapped[str] = mapped_column(String(40)); value: Mapped[str] = mapped_column(String(255)); normalized_value: Mapped[str] = mapped_column(String(255), index=True); primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false"); source: Mapped[str] = mapped_column(String(40), default="manual"); created_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("identifier_type", "normalized_value", name="uq_ci_identifier_value"),)


class CIAlias(Base):
    __tablename__ = "ci_aliases"
    id: Mapped[uuid.UUID] = uid(); ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), index=True); alias: Mapped[str] = mapped_column(String(255)); normalized_alias: Mapped[str] = mapped_column(String(255), index=True); alias_type: Mapped[str] = mapped_column(String(40), default="name"); created_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("ci_id", "normalized_alias", name="uq_ci_alias"),)


class CIRelationshipType(Base):
    __tablename__ = "ci_relationship_types"
    id: Mapped[uuid.UUID] = uid(); name: Mapped[str] = mapped_column(String(100), unique=True); code: Mapped[str] = mapped_column(String(60), unique=True, index=True); inverse_name: Mapped[str] = mapped_column(String(100)); cardinality: Mapped[str] = mapped_column(String(30), default="many_to_many"); directional: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true"); enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class CIRelationship(Base):
    __tablename__ = "ci_relationships"
    id: Mapped[uuid.UUID] = uid(); source_ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), index=True); target_ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), index=True); relationship_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ci_relationship_types.id"), index=True); status: Mapped[str] = mapped_column(String(30), default="active", index=True); source: Mapped[str] = mapped_column(String(40), default="manual"); evidence: Mapped[str | None] = mapped_column(Text); confidence: Mapped[int] = mapped_column(Integer, default=100, server_default="100"); valid_from: Mapped[datetime] = now(); valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); created_by: Mapped[str] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now(); updated_at: Mapped[datetime] = now(); __table_args__ = (CheckConstraint("source_ci_id <> target_ci_id", name="ck_ci_relationship_not_self"), CheckConstraint("confidence BETWEEN 0 AND 100", name="ck_ci_relationship_confidence"), UniqueConstraint("source_ci_id", "target_ci_id", "relationship_type_id", name="uq_ci_relationship"), Index("ix_ci_relationship_endpoints_status", "source_ci_id", "target_ci_id", "status"))


class RelationshipHistory(Base):
    __tablename__ = "ci_relationship_history"
    id: Mapped[uuid.UUID] = uid(); relationship_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ci_relationships.id", ondelete="CASCADE"), index=True); action: Mapped[str] = mapped_column(String(30)); previous_state: Mapped[str | None] = mapped_column(Text); current_state: Mapped[str | None] = mapped_column(Text); reason: Mapped[str | None] = mapped_column(String(1000)); actor_id: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); occurred_at: Mapped[datetime] = now()


class CILifecycleHistory(Base):
    __tablename__ = "ci_lifecycle_history"
    id: Mapped[uuid.UUID] = uid(); ci_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id", ondelete="CASCADE"), index=True); previous_stage: Mapped[str | None] = mapped_column(String(40)); current_stage: Mapped[str] = mapped_column(String(40)); reason: Mapped[str] = mapped_column(String(1000)); actor_id: Mapped[str] = mapped_column(String, ForeignKey("users.id")); occurred_at: Mapped[datetime] = now()


class DependencyGraph(Base):
    __tablename__ = "ci_dependency_graphs"
    id: Mapped[uuid.UUID] = uid(); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); root_ci_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id")); graph_version: Mapped[int] = mapped_column(Integer, default=1); node_count: Mapped[int] = mapped_column(Integer, default=0); edge_count: Mapped[int] = mapped_column(Integer, default=0); checksum_sha256: Mapped[str] = mapped_column(String(64)); graph_data: Mapped[str] = mapped_column(Text); created_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); created_at: Mapped[datetime] = now()


class CIReconciliationCandidate(Base):
    __tablename__ = "ci_reconciliation_candidates"
    id: Mapped[uuid.UUID] = uid(); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); source_type: Mapped[str] = mapped_column(String(40), index=True); source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True); proposed_ci_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("configuration_items.id"), index=True); candidate_name: Mapped[str] = mapped_column(String(220)); identifiers: Mapped[str] = mapped_column(Text, default="{}"); proposed_values: Mapped[str] = mapped_column(Text, default="{}"); score: Mapped[int] = mapped_column(Integer, default=0); match_level: Mapped[str] = mapped_column(String(20), default="none"); evidence: Mapped[str] = mapped_column(Text, default="[]"); conflicts: Mapped[str] = mapped_column(Text, default="[]"); recommended_action: Mapped[str] = mapped_column(String(30), default="review"); status: Mapped[str] = mapped_column(String(30), default="pending", index=True); reviewed_by: Mapped[str | None] = mapped_column(String, ForeignKey("users.id")); reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True)); created_at: Mapped[datetime] = now(); updated_at: Mapped[datetime] = now(); __table_args__ = (UniqueConstraint("source_type", "source_id", name="uq_ci_reconciliation_source"),)


class CIHealthSnapshot(Base):
    __tablename__ = "ci_health_snapshots"
    id: Mapped[uuid.UUID] = uid(); property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), index=True); health_score: Mapped[int] = mapped_column(Integer); total_cis: Mapped[int] = mapped_column(Integer); verified_cis: Mapped[int] = mapped_column(Integer); stale_cis: Mapped[int] = mapped_column(Integer); orphan_cis: Mapped[int] = mapped_column(Integer); duplicate_candidates: Mapped[int] = mapped_column(Integer); missing_owners: Mapped[int] = mapped_column(Integer); relationship_completeness: Mapped[float] = mapped_column(Float); discovery_coverage: Mapped[float] = mapped_column(Float); details: Mapped[str] = mapped_column(Text, default="{}"); calculated_at: Mapped[datetime] = now(); __table_args__ = (CheckConstraint("health_score BETWEEN 0 AND 100", name="ck_ci_health_score"), Index("ix_ci_health_property_time", "property_id", "calculated_at"))
