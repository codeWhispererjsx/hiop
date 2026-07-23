from datetime import datetime, timezone
import logging
from time import monotonic
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
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
from app.core.config import settings
from app.services.ldap_client import (
    LdapClientConfig,
    LdapError,
    SecureLdapClient,
    dn_within,
)

logger = logging.getLogger(__name__)


class ActiveDirectoryConnectionService:
    """Service managing Active Directory connection profiles and credentials."""

    def __init__(
        self, db: Session, client_factory=SecureLdapClient,
        maximum_objects: int | None = None,
    ) -> None:
        self.db = db
        self.repo = ActiveDirectoryConnectionRepository(db)
        self.config_repo = ActiveDirectorySyncConfigurationRepository(db)
        self.client_factory = client_factory
        self.maximum_objects = maximum_objects

    def _get_connection(self, connection_id: str) -> ActiveDirectoryConnection:
        connection = self.repo.get(connection_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active Directory connection was not found.",
            )
        return connection

    def _ensure_no_active_sync(self, connection_id: str) -> None:
        active = self.db.scalar(select(ActiveDirectorySyncRun.id).where(
            ActiveDirectorySyncRun.connection_id == connection_id,
            ActiveDirectorySyncRun.status.in_(("pending", "running")),
        ).limit(1))
        if active:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Connection configuration cannot change during an active synchronization.",
            )

    def _client_config(self, connection: ActiveDirectoryConnection) -> LdapClientConfig:
        return LdapClientConfig(
            connection_id=str(connection.id),
            host=connection.server_host,
            port=connection.server_port,
            use_ssl=connection.use_ssl,
            use_start_tls=connection.use_start_tls,
            verify_tls=connection.verify_tls,
            ca_certificate_reference=connection.ca_certificate_reference,
            authentication_method=connection.authentication_method,
            connect_timeout=connection.connection_timeout_seconds,
            search_timeout=settings.ad_search_timeout_seconds,
            page_size=connection.page_size,
            maximum_page_size=settings.ad_maximum_page_size,
            maximum_objects=self.maximum_objects or settings.ad_maximum_objects_per_query,
            domain_name=connection.domain_name,
            environment=settings.environment,
            allow_insecure_ldap=settings.ad_allow_insecure_ldap,
            approved_hosts=tuple(settings.ad_approved_hosts),
            allow_public_hosts=settings.ad_allow_public_hosts,
            retry_count=settings.ad_connection_retry_count,
        )

    def _validate_connection_policy(self, connection: ActiveDirectoryConnection) -> None:
        try:
            SecureLdapClient(self._client_config(connection)).close()
        except LdapError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"category": error.category, "message": error.safe_message},
            ) from error

    def _bound_client(self, connection: ActiveDirectoryConnection):
        if connection.authentication_method != "anonymous" and not connection.encrypted_bind_secret:
            raise LdapError("configuration_error", "Saved bind credentials are not configured.")
        client = self.client_factory(self._client_config(connection))
        secret = None
        try:
            if connection.encrypted_bind_secret:
                secret = ActiveDirectorySecretService.decrypt_secret(connection.encrypted_bind_secret)
            client.bind(connection.bind_username, secret)
            return client
        except ActiveDirectorySecretError as error:
            client.close()
            raise LdapError("configuration_error", "Saved bind credentials could not be decrypted.") from error
        except Exception:
            client.close()
            raise
        finally:
            secret = None

    @staticmethod
    def _root_scalar(root: dict[str, Any], name: str) -> str | None:
        value = root.get(name)
        if isinstance(value, list):
            return str(value[0]) if value else None
        return str(value) if value else None

    @classmethod
    def safe_root_dse(cls, root: dict[str, Any]) -> dict[str, Any]:
        versions = [str(item) for item in (root.get("supportedLDAPVersion") or [])]
        warnings = []
        if "3" not in versions:
            warnings.append("Server did not report LDAP v3 support.")
        if not root.get("appears_active_directory"):
            warnings.append("Server does not expose the expected Active Directory naming contexts.")
        return {
            "default_naming_context": cls._root_scalar(root, "defaultNamingContext"),
            "root_domain_naming_context": cls._root_scalar(root, "rootDomainNamingContext"),
            "configuration_naming_context": cls._root_scalar(root, "configurationNamingContext"),
            "schema_naming_context": cls._root_scalar(root, "schemaNamingContext"),
            "supported_ldap_versions": versions,
            "supported_sasl_mechanisms": [str(item) for item in (root.get("supportedSASLMechanisms") or [])][:20],
            "dns_host_name": cls._root_scalar(root, "dnsHostName"),
            "server_name": cls._root_scalar(root, "serverName"),
            "appears_active_directory": bool(root.get("appears_active_directory")),
            "ldap_v3_supported": "3" in versions,
            "warnings": warnings,
        }

    def _validate_bases(self, connection, client, root) -> list[str]:
        warnings = []
        default_base = self._root_scalar(root, "defaultNamingContext")
        if not default_base:
            raise LdapError("malformed_response", "Directory did not report a default naming context.")
        if not dn_within(connection.base_dn, default_base) and not dn_within(default_base, connection.base_dn):
            warnings.append("Configured base DN differs from the server default naming context.")
        for label, configured in (
            ("base", connection.base_dn),
            ("user", connection.user_search_base or connection.base_dn),
            ("computer", connection.computer_search_base or connection.base_dn),
            ("group", connection.group_search_base or connection.base_dn),
        ):
            if not dn_within(configured, connection.base_dn):
                raise LdapError("search_base_invalid", f"Configured {label} search base is outside the base DN.")
            if not client.validate_base_dn(configured):
                raise LdapError("base_dn_not_found", f"Configured {label} search base was not found.")
        return warnings

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
                    detail="Active Directory bind secret could not be encrypted. Check server secret configuration.",
                ) from err

        conn_data = payload.model_dump(exclude={"bind_secret"})
        connection = ActiveDirectoryConnection(
            **conn_data,
            encrypted_bind_secret=encrypted_secret,
            created_by=current_user.id,
            updated_by=current_user.id,
        )
        self._validate_connection_policy(connection)
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
        self._ensure_no_active_sync(connection_id)
        connection = self.repo.get(connection_id)
        if not connection:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Active Directory connection '{connection_id}' not found.",
            )

        data = payload.model_dump(exclude_unset=True)
        final_use_ssl = data.get("use_ssl", connection.use_ssl)
        final_use_start_tls = data.get("use_start_tls", connection.use_start_tls)
        if final_use_ssl and final_use_start_tls:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="LDAPS and StartTLS cannot both be enabled.",
            )
        if "name" in data and data["name"] != connection.name:
            existing = self.repo.get_by_name(data["name"])
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"An Active Directory connection named '{data['name']}' already exists.",
                )

        tls_changed = any(
            field in data and data[field] != getattr(connection, field)
            for field in ("use_ssl", "use_start_tls", "verify_tls", "ca_certificate_reference")
        )
        for field, value in data.items():
            setattr(connection, field, value)

        self._validate_connection_policy(connection)
        connection.updated_by = current_user.id

        create_audit_log(
            self.db,
            actor=current_user.username,
            action="AD_CONNECTION_UPDATED",
            entity_type="ActiveDirectoryConnection",
            entity_id=connection.id,
            description=f"Updated Active Directory connection '{connection.name}'.",
        )
        if tls_changed:
            create_audit_log(
                self.db,
                actor=current_user.username,
                action="AD_TLS_SETTINGS_UPDATED",
                entity_type="ActiveDirectoryConnection",
                entity_id=connection.id,
                description=f"Updated TLS policy for Active Directory connection '{connection.name}'.",
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
        self._ensure_no_active_sync(connection_id)
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
                detail="Active Directory bind secret could not be encrypted. Check server secret configuration.",
            ) from err

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
        self._ensure_no_active_sync(connection_id)
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
        connection = self._get_connection(connection_id)
        started = monotonic()
        tested_at = datetime.now(timezone.utc)
        stages: list[dict[str, Any]] = []
        warnings: list[str] = []
        client = None
        create_audit_log(
            self.db, current_user.username, "AD_CONNECTION_TEST_STARTED",
            "ActiveDirectoryConnection", str(connection.id),
            f"Started directory connection test for profile '{connection.name}'.",
        )
        try:
            stage_started = monotonic()
            client = self._bound_client(connection)
            stages.extend([
                {"name": "connection", "status": "passed", "message": "Directory server connection opened.", "duration_ms": int((monotonic() - stage_started) * 1000)},
                {"name": "tls", "status": "passed" if (connection.use_ssl or connection.use_start_tls) else "warning", "message": "TLS policy accepted." if (connection.use_ssl or connection.use_start_tls) else "Development-only plain LDAP policy accepted.", "duration_ms": 0},
                {"name": "bind", "status": "passed", "message": "Directory bind succeeded.", "duration_ms": 0},
            ])
            stage_started = monotonic()
            root = client.get_root_dse()
            safe_root = self.safe_root_dse(root)
            if not safe_root["ldap_v3_supported"]:
                raise LdapError("malformed_response", "Directory server does not report LDAP v3 support.")
            warnings.extend(safe_root["warnings"])
            stages.append({"name": "root_dse", "status": "passed", "message": "RootDSE metadata was read.", "duration_ms": int((monotonic() - stage_started) * 1000)})
            stage_started = monotonic()
            warnings.extend(self._validate_bases(connection, client, root))
            stages.append({"name": "base_dn", "status": "passed", "message": "Configured search bases exist and are within the base DN.", "duration_ms": int((monotonic() - stage_started) * 1000)})
            for label, method, base in (
                ("user_search", client.search_users, connection.user_search_base or connection.base_dn),
                ("computer_search", client.search_computers, connection.computer_search_base or connection.base_dn),
                ("group_search", client.search_groups, connection.group_search_base or connection.base_dn),
            ):
                stage_started = monotonic()
                method(base, limit=1)
                stages.append({"name": label, "status": "passed", "message": "Minimal read permission check succeeded.", "duration_ms": int((monotonic() - stage_started) * 1000)})
            connection.last_test_status = "success"
            connection.last_test_message = "Connection, bind, RootDSE, search bases, and minimal reads succeeded."
            connection.last_successful_bind_at = tested_at
            connection.failure_count = 0
            connection.server_reported_domain = safe_root["default_naming_context"]
            action = "AD_CONNECTION_TEST_SUCCEEDED"
            error = None
            overall = "success"
        except LdapError as failure:
            logger.warning("AD operation failed connection_id=%s operation=test category=%s", connection.id, failure.category)
            connection.last_test_status = "failed"
            connection.last_test_message = failure.safe_message[:500]
            connection.last_failure_at = tested_at
            connection.failure_count = (connection.failure_count or 0) + 1
            stages.append({"name": "failed", "status": "failed", "message": failure.safe_message, "duration_ms": 0})
            action = "AD_CONNECTION_TEST_FAILED"
            error = {"category": failure.category, "message": failure.safe_message, "retryable": failure.retryable}
            overall = "failed"
        finally:
            if client:
                client.close()
        connection.last_tested_at = tested_at
        duration = int((monotonic() - started) * 1000)
        create_audit_log(
            self.db, current_user.username, action,
            "ActiveDirectoryConnection", str(connection.id),
            f"Directory connection test finished with status {overall} in {duration} ms.",
        )
        self.db.commit()
        return {
            "overall_status": overall,
            "connection_id": str(connection.id),
            "stages": stages,
            "warnings": warnings,
            "error": error,
            "tested_at": tested_at,
            "duration_ms": duration,
        }

    def root_dse(self, connection_id: str, current_user: User) -> dict[str, Any]:
        connection = self._get_connection(connection_id)
        if not connection.enabled:
            raise HTTPException(status_code=409, detail="Disabled Active Directory connection cannot be queried.")
        client = None
        try:
            client = self._bound_client(connection)
            result = self.safe_root_dse(client.get_root_dse())
            create_audit_log(self.db, current_user.username, "AD_ROOT_DSE_VIEWED", "ActiveDirectoryConnection", str(connection.id), "Viewed safe RootDSE metadata.")
            self.db.commit()
            return result
        except LdapError as failure:
            logger.warning("AD operation failed connection_id=%s operation=root_dse category=%s", connection.id, failure.category)
            raise HTTPException(status_code=422, detail={"category": failure.category, "message": failure.safe_message}) from failure
        finally:
            if client:
                client.close()

    def preview(
        self,
        connection_id: str,
        object_type: str,
        current_user: User,
        *,
        limit: int,
        search_term: str | None = None,
        enabled: bool | None = None,
        include_members: bool = False,
    ) -> dict[str, Any]:
        connection = self._get_connection(connection_id)
        if not connection.enabled:
            raise HTTPException(status_code=409, detail="Disabled Active Directory connection cannot be queried.")
        if include_members and limit > settings.ad_maximum_groups_with_members:
            raise HTTPException(
                status_code=422,
                detail=f"Full group membership preview is limited to {settings.ad_maximum_groups_with_members} groups.",
            )
        client = None
        try:
            client = self._bound_client(connection)
            root = client.get_root_dse()
            self._validate_bases(connection, client, root)
            base = getattr(connection, f"{object_type[:-1] if object_type.endswith('s') else object_type}_search_base", None) or connection.base_dn
            if object_type == "users":
                result = client.search_users(base, search_term=search_term, enabled=enabled, limit=limit)
                action = "AD_USER_PREVIEW_REQUESTED"
            elif object_type == "computers":
                result = client.search_computers(base, search_term=search_term, enabled=enabled, limit=limit)
                action = "AD_COMPUTER_PREVIEW_REQUESTED"
            elif object_type == "groups":
                result = client.search_groups(
                    base, search_term=search_term, limit=limit,
                    include_members=include_members,
                    member_limit=settings.ad_maximum_group_members,
                )
                action = "AD_GROUP_PREVIEW_REQUESTED"
            else:
                raise HTTPException(status_code=422, detail="Unsupported directory preview type.")
            create_audit_log(self.db, current_user.username, action, "ActiveDirectoryConnection", str(connection.id), f"Requested bounded {object_type} preview; returned {len(result.items)} records.")
            self.db.commit()
            return {
                "object_type": object_type[:-1],
                "items": result.items,
                "returned": len(result.items),
                "truncated": result.truncated,
                "page_count": result.page_count,
                "warnings": result.warnings,
            }
        except LdapError as failure:
            logger.warning("AD operation failed connection_id=%s operation=preview_%s category=%s", connection.id, object_type, failure.category)
            raise HTTPException(status_code=422, detail={"category": failure.category, "message": failure.safe_message}) from failure
        finally:
            if client:
                client.close()


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
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Active Directory sync configuration is missing and must be repaired by an administrator.",
            )
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

    def stage_directory_object(self, *args, **kwargs) -> ActiveDirectoryObject:
        raise NotImplementedError("Directory staging execution is reserved for Epic 3B.")

    def finalize_sync_run(self, *args, **kwargs) -> ActiveDirectorySyncRun:
        raise NotImplementedError("Directory synchronization is reserved for Epic 3B.")

    def mark_missing_objects(self, *args, **kwargs) -> int:
        raise NotImplementedError("Directory synchronization is reserved for Epic 3B.")


class ActiveDirectoryMatchingService:
    """Service skeleton for directory object candidate matching (Epic 3A stub)."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ActiveDirectoryMatchCandidateRepository(db)

    def generate_user_candidates(self, *args, **kwargs) -> list[ActiveDirectoryMatchCandidate]:
        raise NotImplementedError("Active Directory matching is reserved for Epic 3B.")

    def generate_device_candidates(self, *args, **kwargs) -> list[ActiveDirectoryMatchCandidate]:
        raise NotImplementedError("Active Directory matching is reserved for Epic 3B.")

    def resolve_candidate(self, *args, **kwargs) -> ActiveDirectoryMatchCandidate:
        raise NotImplementedError("Active Directory match resolution is reserved for Epic 3B.")
