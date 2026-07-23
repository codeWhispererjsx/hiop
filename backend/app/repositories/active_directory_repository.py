from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncRun,
)


class ActiveDirectoryConnectionRepository:
    """Persistence repository for Active Directory connection configurations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, connection: ActiveDirectoryConnection) -> ActiveDirectoryConnection:
        self.db.add(connection)
        return connection

    def get(self, connection_id: str) -> ActiveDirectoryConnection | None:
        return self.db.get(ActiveDirectoryConnection, connection_id)

    def get_by_name(self, name: str) -> ActiveDirectoryConnection | None:
        statement = select(ActiveDirectoryConnection).where(ActiveDirectoryConnection.name == name)
        return self.db.scalar(statement)

    def page(
        self,
        *,
        search: str | None = None,
        enabled_only: bool | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[Sequence[ActiveDirectoryConnection], int]:
        filters = []
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    ActiveDirectoryConnection.name.ilike(pattern),
                    ActiveDirectoryConnection.domain_name.ilike(pattern),
                    ActiveDirectoryConnection.server_host.ilike(pattern),
                )
            )
        if enabled_only is not None:
            filters.append(ActiveDirectoryConnection.enabled == enabled_only)

        total = self.db.scalar(select(func.count(ActiveDirectoryConnection.id)).where(*filters)) or 0
        statement = (
            select(ActiveDirectoryConnection)
            .where(*filters)
            .order_by(ActiveDirectoryConnection.name)
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(statement).all(), total

    def delete(self, connection: ActiveDirectoryConnection) -> None:
        self.db.delete(connection)


class ActiveDirectorySyncConfigurationRepository:
    """Persistence repository for AD sync configurations."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, sync_config: ActiveDirectorySyncConfiguration) -> ActiveDirectorySyncConfiguration:
        self.db.add(sync_config)
        return sync_config

    def get_by_connection(self, connection_id: str) -> ActiveDirectorySyncConfiguration | None:
        statement = select(ActiveDirectorySyncConfiguration).where(
            ActiveDirectorySyncConfiguration.connection_id == connection_id
        )
        return self.db.scalar(statement)


class ActiveDirectoryObjectRepository:
    """Persistence repository for directory objects (users, computers, groups)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, obj: ActiveDirectoryObject) -> ActiveDirectoryObject:
        self.db.add(obj)
        return obj

    def get(self, object_id: str) -> ActiveDirectoryObject | None:
        return self.db.get(ActiveDirectoryObject, object_id)

    def get_by_guid(self, connection_id: str, object_guid: str) -> ActiveDirectoryObject | None:
        statement = select(ActiveDirectoryObject).where(
            ActiveDirectoryObject.connection_id == connection_id,
            ActiveDirectoryObject.object_guid == object_guid,
        )
        return self.db.scalar(statement)

    def page(
        self,
        *,
        connection_id: str | None = None,
        object_type: str | None = None,
        sync_status: str | None = None,
        review_status: str | None = None,
        search: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[Sequence[ActiveDirectoryObject], int]:
        filters = []
        if connection_id:
            filters.append(ActiveDirectoryObject.connection_id == connection_id)
        if object_type:
            filters.append(ActiveDirectoryObject.object_type == object_type)
        if sync_status:
            filters.append(ActiveDirectoryObject.sync_status == sync_status)
        if review_status:
            filters.append(ActiveDirectoryObject.review_status == review_status)
        if search:
            pattern = f"%{search.strip()}%"
            filters.append(
                or_(
                    ActiveDirectoryObject.sam_account_name.ilike(pattern),
                    ActiveDirectoryObject.display_name.ilike(pattern),
                    ActiveDirectoryObject.dns_hostname.ilike(pattern),
                    ActiveDirectoryObject.distinguished_name.ilike(pattern),
                    ActiveDirectoryObject.email.ilike(pattern),
                )
            )

        total = self.db.scalar(select(func.count(ActiveDirectoryObject.id)).where(*filters)) or 0
        statement = (
            select(ActiveDirectoryObject)
            .where(*filters)
            .order_by(ActiveDirectoryObject.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(statement).all(), total


class ActiveDirectorySyncRunRepository:
    """Persistence repository for AD sync run history."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, run: ActiveDirectorySyncRun) -> ActiveDirectorySyncRun:
        self.db.add(run)
        return run

    def get(self, run_id: str) -> ActiveDirectorySyncRun | None:
        return self.db.get(ActiveDirectorySyncRun, run_id)

    def page(
        self,
        *,
        connection_id: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[Sequence[ActiveDirectorySyncRun], int]:
        filters = []
        if connection_id:
            filters.append(ActiveDirectorySyncRun.connection_id == connection_id)
        if status:
            filters.append(ActiveDirectorySyncRun.status == status)

        total = self.db.scalar(select(func.count(ActiveDirectorySyncRun.id)).where(*filters)) or 0
        statement = (
            select(ActiveDirectorySyncRun)
            .where(*filters)
            .order_by(ActiveDirectorySyncRun.started_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(statement).all(), total


class ActiveDirectoryMatchCandidateRepository:
    """Persistence repository for directory match candidates."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, candidate: ActiveDirectoryMatchCandidate) -> ActiveDirectoryMatchCandidate:
        self.db.add(candidate)
        return candidate

    def get(self, candidate_id: str) -> ActiveDirectoryMatchCandidate | None:
        return self.db.get(ActiveDirectoryMatchCandidate, candidate_id)

    def page(
        self,
        *,
        directory_object_id: str | None = None,
        candidate_type: str | None = None,
        match_status: str | None = None,
        offset: int = 0,
        limit: int = 25,
    ) -> tuple[Sequence[ActiveDirectoryMatchCandidate], int]:
        filters = []
        if directory_object_id:
            filters.append(ActiveDirectoryMatchCandidate.directory_object_id == directory_object_id)
        if candidate_type:
            filters.append(ActiveDirectoryMatchCandidate.candidate_type == candidate_type)
        if match_status:
            filters.append(ActiveDirectoryMatchCandidate.match_status == match_status)

        total = self.db.scalar(select(func.count(ActiveDirectoryMatchCandidate.id)).where(*filters)) or 0
        statement = (
            select(ActiveDirectoryMatchCandidate)
            .where(*filters)
            .order_by(ActiveDirectoryMatchCandidate.match_score.desc())
            .offset(offset)
            .limit(limit)
        )
        return self.db.scalars(statement).all(), total
