"""Persistence-only repositories for SNMP foundation entities."""
from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.snmp import (
    SNMPCredential, SNMPDeviceProfile, SNMPDiscoveryCandidate, SNMPInterface,
    SNMPMetric, SNMPOIDDefinition, SNMPPollingConfiguration, SNMPPollRun,
    SNMPTarget,
)

T = TypeVar("T")


class SNMPRepository(Generic[T]):
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
        items = self.db.scalars(
            query.order_by(getattr(self.model, "created_at").desc())
            .offset((page - 1) * page_size).limit(page_size)
        ).all()
        return list(items), total


class SNMPCredentialRepository(SNMPRepository[SNMPCredential]):
    model = SNMPCredential


class SNMPTargetRepository(SNMPRepository[SNMPTarget]):
    model = SNMPTarget


class SNMPDeviceProfileRepository(SNMPRepository[SNMPDeviceProfile]):
    model = SNMPDeviceProfile


class SNMPOIDDefinitionRepository(SNMPRepository[SNMPOIDDefinition]):
    model = SNMPOIDDefinition


class SNMPPollingConfigurationRepository(SNMPRepository[SNMPPollingConfiguration]):
    model = SNMPPollingConfiguration

    def for_target(self, target_id: UUID):
        return self.db.scalar(select(self.model).where(self.model.target_id == target_id))


class SNMPPollRunRepository(SNMPRepository[SNMPPollRun]):
    model = SNMPPollRun


class SNMPMetricRepository(SNMPRepository[SNMPMetric]):
    model = SNMPMetric


class SNMPInterfaceRepository(SNMPRepository[SNMPInterface]):
    model = SNMPInterface

    def for_target_index(self, target_id: UUID, interface_index: int):
        return self.db.scalar(select(self.model).where(
            self.model.target_id == target_id,
            self.model.interface_index == interface_index,
        ))


class SNMPDiscoveryCandidateRepository(SNMPRepository[SNMPDiscoveryCandidate]):
    model = SNMPDiscoveryCandidate
