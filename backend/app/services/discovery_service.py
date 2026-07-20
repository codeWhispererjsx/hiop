"""Discovery orchestration contract.

Epic 1A intentionally defines signatures only. Network access, matching,
review, approval, inventory mutation, and scheduling belong to later epics.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.discovered_device import DiscoveredDevice, DiscoveryRun


class DiscoveryService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def start_run(self, range_scanned: str, trigger_type: str, triggered_by: str | None = None) -> DiscoveryRun:
        raise NotImplementedError

    def record_observation(self, run_id: UUID, observation: dict) -> DiscoveredDevice:
        raise NotImplementedError

    def match_observation(self, observation: dict) -> DiscoveredDevice | None:
        raise NotImplementedError

    def complete_run(self, run_id: UUID, summary: dict) -> DiscoveryRun:
        raise NotImplementedError

    def fail_run(self, run_id: UUID, error_summary: str) -> DiscoveryRun:
        raise NotImplementedError
