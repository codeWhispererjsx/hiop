"""Persistence-only repositories for topology entities."""
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.topology import (
    DeviceDependency, NetworkSegment, Topology, TopologyChange, TopologyGroup,
    TopologyLink, TopologyLinkEvidence, TopologyNode, TopologyNodePosition,
    TopologyNodeSegment, TopologySnapshot,
)

T = TypeVar("T")


class TopologyRepository(Generic[T]):
    model: type[T]

    def __init__(self, db: Session):
        self.db = db

    def get(self, object_id: UUID) -> T | None:
        return self.db.get(self.model, object_id)

    def add(self, row: T) -> T:
        self.db.add(row)
        return row

    def update(self, row: T, values: dict[str, Any]) -> T:
        for key, value in values.items():
            setattr(row, key, value)
        return row

    def list(self, *, page: int = 1, page_size: int = 50, filters: dict[str, Any] | None = None):
        query = select(self.model)
        count = select(func.count()).select_from(self.model)
        for key, value in (filters or {}).items():
            if value is not None and hasattr(self.model, key):
                clause = getattr(self.model, key) == value
                query, count = query.where(clause), count.where(clause)
        total = self.db.scalar(count) or 0
        if hasattr(self.model, "created_at"):
            query = query.order_by(getattr(self.model, "created_at").desc())
        items = self.db.scalars(query.offset((page - 1) * page_size).limit(page_size)).all()
        return list(items), total


class TopologyDefinitionRepository(TopologyRepository[Topology]): model = Topology
class TopologyNodeRepository(TopologyRepository[TopologyNode]): model = TopologyNode


class TopologyLinkRepository(TopologyRepository[TopologyLink]):
    model = TopologyLink

    def neighbors(self, topology_id: UUID, node_id: UUID):
        return list(self.db.scalars(select(self.model).where(
            self.model.topology_id == topology_id,
            self.model.is_suppressed.is_(False),
            or_(self.model.source_node_id == node_id, self.model.target_node_id == node_id),
        )).all())


class TopologyLinkEvidenceRepository(TopologyRepository[TopologyLinkEvidence]): model = TopologyLinkEvidence
class NetworkSegmentRepository(TopologyRepository[NetworkSegment]): model = NetworkSegment
class TopologyNodeSegmentRepository(TopologyRepository[TopologyNodeSegment]): model = TopologyNodeSegment
class DeviceDependencyRepository(TopologyRepository[DeviceDependency]): model = DeviceDependency
class TopologySnapshotRepository(TopologyRepository[TopologySnapshot]): model = TopologySnapshot
class TopologyChangeRepository(TopologyRepository[TopologyChange]): model = TopologyChange
class TopologyNodePositionRepository(TopologyRepository[TopologyNodePosition]): model = TopologyNodePosition
class TopologyGroupRepository(TopologyRepository[TopologyGroup]): model = TopologyGroup
