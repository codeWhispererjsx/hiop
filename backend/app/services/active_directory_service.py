from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectoryMatchCandidate,
    ActiveDirectoryObject,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncRun,
)
from app.models.user import User
from app.repositories.active_directory_repository import (
    ActiveDirectoryConnectionRepository,
    ActiveDirectoryMatchCandidateRepository,
    ActiveDirectoryObjectRepository,
    ActiveDirectorySyncConfigurationRepository,
    ActiveDirectorySyncRunRepository,
)
from app.schemas.active_directory import (
    ActiveDirectoryConnectionCreate,
    ActiveDirectoryConnectionUpdate,
    ActiveDirectorySyncConfigurationUpdate,
)
from app.services.active_directory_secret_service import (
    ActiveDirectorySecretError,
    ActiveDirectorySecretService,
)
from app.services.audit_service import create_audit_log
from app.services.ldap_client import MockLdapClient


class ActiveDirectoryConnectionService:
    """Service managing Active Directory connection profiles and credentials."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ActiveDirectoryConnectionRepository(db)
        self.config_repo = ActiveDirectorySyncConfigurationRepository(db)

    def create_connection(
        self,
        payload: ActiveDirectoryConnectionCreate,
        current_user: User,
    ) -> ActiveDirectoryConnection:
        existing = self.repo.get_by_name(payload.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"An Active Directory connection named '{payload.name}' already exists.",
            )

        encrypted_secret = None
        if payload.bind_secret:
            try:
                encrypted_secret = ActiveDirectorySecretService.encrypt_secret(payload.bind_secret)
            except ActiveDirectorySecretError as err:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to encrypt bind secret: {err}",
                )

        conn_data = payload.model_dump(exclude={"bind_secret"})
        connection = ActiveDirectoryConnection(
            **conn_data,
            encrypted_bind_secret=encrypted_secret,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        self.repo.add(connection)
        self.db.flush()

        # Create default sync configuration alongside connection
        sync_config = ActiveDirectorySyncConfiguration(
            connection_id=connection.id,
            enabled=True,
        )
        self.config_repo.add(sync_config)

        create_audit_log(
            self.db,
            actor=current_user.username,
            action="AD_CONNECTION_CREATED",
            entity_type="ActiveDirectoryConnection",
            entity_id=connection.id,
            description=f"Created Active Directory connection '{connection.name}' for domain '{connection.domain_name}'.",
        )

        self.db.commit()
        self.db.refresh(connection)
        return connection

    def update_connection(
        self,
        connection_id: str,
        payload: ActiveDirectoryConnectionUpdate,
        current_user: User,
    ) -> ActiveDirectoryConnection:
        connection = self.repo.get(connection_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active Directory connection '{connection_id}' not found.",
            )

        data = payload.model_dump(exclude_unset=True)
        if "name" in data and data["name"] != connection.name:
            existing = self.repo.get_by_name(data["name"])
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"An Active Directory connection named '{data['name']}' already exists.",
                )

        for field, value in data.items():
            setattr(connection, field, value)

        connection.updated_by = current_user.id

        create_audit_log(
            self.db,
            actor=current_user.username,
            action="AD_CONNECTION_UPDATED",
            entity_type="ActiveDirectoryConnection",
            entity_id=connection.id,
            description=f"Updated Active Directory connection '{connection.name}'.",
        )

        self.db.commit()
        self.db.refresh(connection)
        return connection

    def rotate_secret(
        self,
        connection_id: str,
        new_secret: str,
        current_user: User,
    ) -> ActiveDirectoryConnection:
        connection = self.repo.get(connection_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active Directory connection '{connection_id}' not found.",
            )

        try:
            encrypted_secret = ActiveDirectorySecretService.encrypt_secret(new_secret)
        except ActiveDirectorySecretError as err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to encrypt bind secret: {err}",
            )

        connection.encrypted_bind_secret = encrypted_secret
        connection.updated_by = current_user.id

        create_audit_log(
            self.db,
            actor=current_user.username,
            action="AD_SECRET_ROTATED",
            entity_type="ActiveDirectoryConnection",
            entity_id=connection.id,
            description=f"Rotated bind secret for Active Directory connection '{connection.name}'.",
        )

        self.db.commit()
        self.db.refresh(connection)
        return connection

    def disable_connection(
        self,
        connection_id: str,
        current_user: User,
    ) -> ActiveDirectoryConnection:
        connection = self.repo.get(connection_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active Directory connection '{connection_id}' not found.",
            )

        connection.enabled = False
        connection.updated_by = current_user.id

        create_audit_log(
            self.db,
            actor=current_user.username,
            action="AD_CONNECTION_DISABLED",
            entity_type="ActiveDirectoryConnection",
            entity_id=connection.id,
            description=f"Disabled Active Directory connection '{connection.name}'.",
        )

        self.db.commit()
        self.db.refresh(connection)
        return connection

    def test_connection(
        self,
        connection_id: str,
        current_user: User,
    ) -> dict[str, Any]:
        connection = self.repo.get(connection_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active Directory connection '{connection_id}' not found.",
            )

        # Epic 3A uses safe mock client stub only (no live domain access)
        client = MockLdapClient(
            host=connection.server_host,
            port=connection.server_port,
            use_ssl=connection.use_ssl,
        )
        result = client.test_connection()

        connection.last_tested_at = datetime.now(timezone.utc)
        connection.last_test_status = "success" if result["success"] else "failed"
        connection.last_test_message = result["message"]

        create_audit_log(
            self.db,
            actor=current_user.username,
            action="AD_CONNECTION_TESTED",
            entity_type="ActiveDirectoryConnection",
            entity_id=connection.id,
            description=f"Tested Active Directory connection '{connection.name}' (mock stub mode). Result: {connection.last_test_status}.",
        )

        self.db.commit()
        return result


class ActiveDirectorySyncConfigService:
    """Service managing Active Directory sync configuration profiles."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ActiveDirectorySyncConfigurationRepository(db)
        self.conn_repo = ActiveDirectoryConnectionRepository(db)

    def get_sync_config(self, connection_id: str) -> ActiveDirectorySyncConfiguration:
        config = self.repo.get_by_connection(connection_id)
        if not config:
            connection = self.conn_repo.get(connection_id)
            if not connection:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Active Directory connection '{connection_id}' not found.",
                )
            # Create default config if missing
            config = ActiveDirectorySyncConfiguration(connection_id=connection_id, enabled=True)
            self.repo.add(config)
            self.db.commit()
            self.db.refresh(config)
        return config

    def update_sync_config(
        self,
        connection_id: str,
        payload: ActiveDirectorySyncConfigurationUpdate,
        current_user: User,
    ) -> ActiveDirectorySyncConfiguration:
        config = self.get_sync_config(connection_id)
        data = payload.model_dump(exclude_unset=True)

        for field, value in data.items():
            setattr(config, field, value)

        create_audit_log(
            self.db,
            actor=current_user.username,
            action="AD_SYNC_CONFIG_UPDATED",
            entity_type="ActiveDirectorySyncConfiguration",
            entity_id=config.id,
            description=f"Updated AD sync configuration for connection '{connection_id}'.",
        )

        self.db.commit()
        self.db.refresh(config)
        return config


class ActiveDirectorySyncService:
    """Service skeleton for directory object staging and sync runs (Epic 3A stub)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ActiveDirectorySyncRunRepository(db)
        self.obj_repo = ActiveDirectoryObjectRepository(db)

    def create_sync_run(
        self,
        connection_id: str,
        triggered_by: str | None = None,
        dry_run: bool = True,
    ) -> ActiveDirectorySyncRun:
        run = ActiveDirectorySyncRun(
            connection_id=connection_id,
            triggered_by=triggered_by,
            dry_run=dry_run,
            status="pending",
        )
        self.repo.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run


class ActiveDirectoryMatchingService:
    """Service skeleton for directory object candidate matching (Epic 3A stub)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ActiveDirectoryMatchCandidateRepository(db)
