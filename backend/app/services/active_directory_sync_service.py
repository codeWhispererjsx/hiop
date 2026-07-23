"""Manual Active Directory synchronization into staging only.

The orchestrator deliberately never creates or updates HIOP users or devices.
It uses bounded LDAP queries, batch commits, persistent progress, and conservative
checkpoint/missing-object rules.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any, Callable

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectoryObject,
    ActiveDirectoryObjectChange,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncError,
    ActiveDirectorySyncRun,
)
from app.models.user import User
from app.models.system_setting import SystemSetting
from app.services.active_directory_service import ActiveDirectoryConnectionService
from app.services.audit_service import create_audit_log
from app.services.email_service import send_email
from app.services.settings_service import DEFAULTS
from app.services.ldap_client import LdapError, SecureLdapClient
from app.websocket.connection_manager import manager

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")
TERMINAL_STATUSES = ("completed", "partial", "failed", "cancelled")
TRANSITIONS = {
    "pending": {"running", "cancelled", "failed"},
    "running": {"completed", "partial", "failed", "cancelled"},
}
OBJECT_METHODS = {
    "user": "search_users",
    "computer": "search_computers",
    "group": "search_groups",
}
TRACKED_FIELDS = (
    "object_sid", "distinguished_name", "sam_account_name", "user_principal_name",
    "common_name", "display_name", "dns_hostname", "email", "department",
    "job_title", "operating_system", "operating_system_version",
    "organizational_unit", "description", "enabled", "last_logon_at",
    "when_created", "when_changed", "raw_attributes",
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return sorted((_json_value(v) for v in value), key=lambda item: str(item).casefold())
    return value


def canonical_directory_values(item: dict[str, Any], object_type: str) -> dict[str, Any]:
    """Return the approved, normalized staging representation."""
    def text(name: str, *, lower: bool = False) -> str | None:
        value = item.get(name)
        if value is None or not str(value).strip():
            return None
        value = str(value).strip()
        return value.casefold() if lower else value

    dn = text("distinguished_name") or ""
    extras: dict[str, Any] = {}
    for key in ("group_memberships", "managed_by", "group_type", "members",
                "members_truncated", "member_count_returned", "parse_warnings"):
        if key in item:
            extras[key] = _json_value(item[key])
    values = {
        "object_sid": text("object_sid"),
        "distinguished_name": ",".join(part.strip() for part in dn.split(",")),
        "sam_account_name": text("sam_account_name", lower=True),
        "user_principal_name": text("user_principal_name", lower=True),
        "common_name": text("common_name"),
        "display_name": text("display_name"),
        "dns_hostname": text("dns_hostname", lower=True),
        "email": text("email", lower=True),
        "department": text("department"),
        "job_title": text("job_title"),
        "operating_system": text("operating_system"),
        "operating_system_version": text("operating_system_version"),
        "organizational_unit": text("organizational_unit"),
        "description": text("description"),
        "enabled": bool(item.get("enabled", True)),
        "last_logon_at": item.get("last_logon_at"),
        "when_created": item.get("when_created"),
        "when_changed": item.get("when_changed"),
        "raw_attributes": extras,
    }
    if object_type == "group" and isinstance(extras.get("members"), list):
        extras["members"] = sorted(set(extras["members"]), key=str.casefold)
    return values


def stable_identity(item: dict[str, Any]) -> tuple[str, str]:
    guid = str(item.get("object_guid") or "").strip().lower()
    if guid:
        return f"guid:{guid}", guid
    sid = str(item.get("object_sid") or "").strip()
    if sid:
        return f"sid:{sid}", f"sid:{sid}"
    dn = ",".join(part.strip().casefold() for part in str(item.get("distinguished_name") or "").split(","))
    if not dn:
        raise ValueError("Directory object has no stable GUID, SID, or distinguished name.")
    digest = hashlib.sha256(dn.encode("utf-8")).hexdigest()
    return f"dn:{digest}", f"dn:{digest}"


def content_hash(values: dict[str, Any]) -> str:
    payload = json.dumps(_json_value(values), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def classify_change(before: dict[str, Any], after: dict[str, Any], was_missing: bool) -> str:
    if was_missing:
        return "restored"
    if before.get("enabled") is True and after.get("enabled") is False:
        return "disabled"
    if before.get("enabled") is False and after.get("enabled") is True:
        return "enabled"
    if before.get("distinguished_name") != after.get("distinguished_name"):
        return "moved"
    rename_fields = ("sam_account_name", "common_name", "display_name", "dns_hostname")
    if any(before.get(key) != after.get(key) for key in rename_fields):
        return "renamed"
    return "updated"


class ActiveDirectorySynchronizationService:
    def __init__(
        self,
        db: Session,
        *,
        client_factory: Callable[..., Any] = SecureLdapClient,
        publisher: Callable[[dict[str, Any]], None] = manager.broadcast_from_thread,
        email_sender: Callable[..., None] = send_email,
    ) -> None:
        self.db = db
        self.client_factory = client_factory
        self.publisher = publisher
        self.email_sender = email_sender

    def _notify_admin(self, run: ActiveDirectorySyncRun) -> None:
        try:
            stored = {
                row.key: row.value for row in self.db.query(SystemSetting).filter(
                    SystemSetting.key.in_((
                        "notifications.email_notifications",
                        "notifications.recipient_email",
                    ))
                ).all()
            }
            enabled = stored.get(
                "notifications.email_notifications",
                DEFAULTS["notifications.email_notifications"],
            ).lower() == "true"
            recipient = stored.get("notifications.recipient_email") or None
            if enabled:
                self.email_sender(
                    subject=f"HIOP directory sync {run.status}",
                    body=(
                        f"Synchronization {run.id} finished as {run.status}. "
                        f"Created {run.created_objects}, updated {run.updated_objects}, "
                        f"missing {run.missing_objects}, errors {run.errors_count}."
                    ),
                    recipient=recipient,
                )
        except Exception:
            logger.exception("AD synchronization notification failed run_id=%s", run.id)

    def _audit(self, run: ActiveDirectorySyncRun, actor: str, action: str, description: str) -> None:
        create_audit_log(
            self.db, actor=actor, action=action, entity_type="ActiveDirectorySyncRun",
            entity_id=run.id, description=description,
        )

    def _publish(self, event: str, run: ActiveDirectorySyncRun, **extra: Any) -> None:
        self.publisher({
            "type": event, "sync_run_id": run.id, "connection_id": run.connection_id,
            "status": run.status, **extra,
        })

    @staticmethod
    def _transition(run: ActiveDirectorySyncRun, target: str) -> None:
        if target not in TRANSITIONS.get(run.status, set()):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Cannot transition sync from {run.status} to {target}.")
        run.status = target

    def _connection_and_config(
        self, connection_id: str
    ) -> tuple[ActiveDirectoryConnection, ActiveDirectorySyncConfiguration]:
        connection = self.db.get(ActiveDirectoryConnection, connection_id)
        if not connection:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Active Directory connection was not found.")
        if not connection.enabled:
            raise HTTPException(status.HTTP_409_CONFLICT, "Disabled connections cannot be synchronized.")
        config = self.db.scalar(select(ActiveDirectorySyncConfiguration).where(
            ActiveDirectorySyncConfiguration.connection_id == connection_id
        ))
        if not config or not config.enabled:
            raise HTTPException(status.HTTP_409_CONFLICT, "Directory synchronization is not enabled.")
        return connection, config

    def start(
        self,
        connection_id: str,
        actor: User,
        *,
        sync_mode: str,
        dry_run: bool | None,
        object_types: list[str] | None,
        limit: int | None,
    ) -> ActiveDirectorySyncRun:
        connection, config = self._connection_and_config(connection_id)
        existing = self.db.scalar(select(ActiveDirectorySyncRun.id).where(
            ActiveDirectorySyncRun.connection_id == connection_id,
            ActiveDirectorySyncRun.status.in_(ACTIVE_STATUSES),
        ).limit(1))
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "A synchronization is already active for this connection.")
        enabled = {
            "user": config.sync_users_enabled,
            "computer": config.sync_computers_enabled,
            "group": config.sync_groups_enabled,
        }
        requested = object_types or [name for name, allowed in enabled.items() if allowed]
        requested = list(dict.fromkeys(requested))
        if not requested or any(name not in OBJECT_METHODS or not enabled[name] for name in requested):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Requested object types are not enabled.")
        effective_limit = min(limit or settings.ad_maximum_objects_per_sync, settings.ad_maximum_objects_per_sync)
        run = ActiveDirectorySyncRun(
            connection_id=connection.id,
            triggered_by=actor.id,
            trigger_type="manual",
            dry_run=config.dry_run_default if dry_run is None else dry_run,
            sync_mode=sync_mode,
            object_types=requested,
            checkpoint_before=dict(config.checkpoints or {}),
            checkpoint_after=dict(config.checkpoints or {}),
            progress={"objects_processed": 0, "pages_processed": 0, "limit": effective_limit},
        )
        self.db.add(run)
        self.db.flush()
        self._audit(run, actor.username, "AD_SYNC_REQUESTED", f"Manual {sync_mode} AD staging sync requested.")
        self.db.commit()
        self.db.refresh(run)
        return self.execute(run.id, actor, effective_limit=effective_limit)

    def _cancelled(self, run: ActiveDirectorySyncRun) -> bool:
        self.db.refresh(run)
        return run.cancel_requested_at is not None

    def _record_error(
        self, run: ActiveDirectorySyncRun, object_type: str | None, stage: str,
        code: str, message: str, *, reference: str | None = None, retryable: bool = False,
    ) -> None:
        self.db.add(ActiveDirectorySyncError(
            sync_run_id=run.id, object_type=object_type,
            safe_object_reference=(reference or "")[:128] or None,
            stage=stage, error_code=code, safe_message=message[:500], retryable=retryable,
        ))
        run.errors_count += 1

    def _existing(self, connection_id: str, identity: str, guid_value: str) -> ActiveDirectoryObject | None:
        if identity.startswith("guid:"):
            condition = ActiveDirectoryObject.object_guid == guid_value
        elif identity.startswith("sid:"):
            condition = ActiveDirectoryObject.object_sid == identity[4:]
        else:
            condition = ActiveDirectoryObject.object_guid == guid_value
        return self.db.scalar(select(ActiveDirectoryObject).where(
            ActiveDirectoryObject.connection_id == connection_id, condition
        ).limit(1))

    def _compare(self, obj: ActiveDirectoryObject, values: dict[str, Any]) -> tuple[list[str], dict, dict]:
        before, after, changed = {}, {}, []
        for field in TRACKED_FIELDS:
            old, new = _json_value(getattr(obj, field)), _json_value(values[field])
            if old != new:
                changed.append(field)
                before[field], after[field] = old, new
        return changed, before, after

    def _stage_item(
        self, run: ActiveDirectorySyncRun, object_type: str, item: dict[str, Any],
        now: datetime, *, dry_run: bool,
    ) -> str:
        identity, guid_value = stable_identity(item)
        values = canonical_directory_values(item, object_type)
        if not values["distinguished_name"]:
            raise ValueError("Directory object distinguished name is missing.")
        obj = self._existing(run.connection_id, identity, guid_value)
        if not obj:
            if not dry_run:
                obj = ActiveDirectoryObject(
                    connection_id=run.connection_id, object_guid=guid_value,
                    object_type=object_type, first_seen_at=now, last_seen_at=now,
                    last_sync_run_id=run.id, sync_status="discovered",
                    content_hash=content_hash(values), **values,
                )
                self.db.add(obj)
                self.db.flush()
                self.db.add(ActiveDirectoryObjectChange(
                    directory_object_id=obj.id, sync_run_id=run.id, change_type="created",
                    changed_fields=list(TRACKED_FIELDS), before_values={},
                    after_values={key: _json_value(values[key]) for key in TRACKED_FIELDS},
                ))
            return "created"
        changed, before, after = self._compare(obj, values)
        was_missing = obj.sync_status == "missing"
        if not changed and not was_missing:
            if not dry_run:
                obj.last_seen_at = now
                obj.last_sync_run_id = run.id
                obj.sync_status = "unchanged"
            return "unchanged"
        change_type = classify_change(before, after, was_missing)
        if not dry_run:
            for field, value in values.items():
                setattr(obj, field, value)
            obj.last_seen_at = now
            obj.last_sync_run_id = run.id
            obj.missing_since = None
            obj.sync_status = "changed"
            obj.content_hash = content_hash(values)
            self.db.add(ActiveDirectoryObjectChange(
                directory_object_id=obj.id, sync_run_id=run.id, change_type=change_type,
                changed_fields=changed or ["sync_status"], before_values=before,
                after_values=after,
            ))
        return "restored" if was_missing else "updated"

    def _mark_missing(
        self, run: ActiveDirectorySyncRun, object_type: str, now: datetime
    ) -> int:
        threshold = now - timedelta(minutes=settings.ad_sync_missing_grace_period_minutes)
        objects = self.db.scalars(select(ActiveDirectoryObject).where(
            ActiveDirectoryObject.connection_id == run.connection_id,
            ActiveDirectoryObject.object_type == object_type,
            or_(
                ActiveDirectoryObject.last_sync_run_id.is_(None),
                ActiveDirectoryObject.last_sync_run_id != run.id,
            ),
            ActiveDirectoryObject.last_seen_at <= threshold,
            ActiveDirectoryObject.sync_status != "missing",
        )).all()
        for obj in objects:
            obj.sync_status = "missing"
            obj.missing_since = now
            self.db.add(ActiveDirectoryObjectChange(
                directory_object_id=obj.id, sync_run_id=run.id, change_type="missing",
                changed_fields=["sync_status", "missing_since"],
                before_values={"sync_status": "unchanged"},
                after_values={"sync_status": "missing", "missing_since": now.isoformat()},
            ))
        return len(objects)

    def execute(self, run_id: str, actor: User, *, effective_limit: int | None = None) -> ActiveDirectorySyncRun:
        run = self.db.get(ActiveDirectorySyncRun, run_id)
        if not run:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Synchronization run was not found.")
        if run.status != "pending":
            raise HTTPException(status.HTTP_409_CONFLICT, "Only pending synchronization runs can start.")
        connection, config = self._connection_and_config(run.connection_id)
        limit = min(effective_limit or settings.ad_maximum_objects_per_sync, settings.ad_maximum_objects_per_sync)
        started = monotonic()
        client = None
        had_partial = False
        self._transition(run, "running")
        self._audit(run, actor.username, "AD_SYNC_STARTED", "AD staging synchronization started.")
        self.db.commit()
        self._publish("ad_sync_started", run, dry_run=run.dry_run, sync_mode=run.sync_mode)
        try:
            client = ActiveDirectoryConnectionService(
                self.db, client_factory=self.client_factory, maximum_objects=limit
            )._bound_client(connection)
            for object_type in run.object_types:
                if self._cancelled(run):
                    self._transition(run, "cancelled")
                    break
                since = None
                checkpoint = (run.checkpoint_before or {}).get(object_type)
                if run.sync_mode == "incremental" and checkpoint:
                    since = datetime.fromisoformat(checkpoint) - timedelta(
                        minutes=settings.ad_sync_incremental_overlap_minutes
                    )
                base = {
                    "user": connection.user_search_base,
                    "computer": connection.computer_search_base,
                    "group": connection.group_search_base,
                }[object_type] or connection.base_dn
                try:
                    result = getattr(client, OBJECT_METHODS[object_type])(
                        base, limit=limit, changed_since=since,
                        include_members=(object_type == "group" and config.sync_group_memberships),
                        member_limit=settings.ad_maximum_group_members,
                    )
                    unique: dict[str, dict[str, Any]] = {}
                    for item in result.items:
                        try:
                            identity, _ = stable_identity(item)
                            unique[identity] = item
                        except ValueError:
                            self._record_error(run, object_type, "conversion", "missing_identity",
                                               "Directory object did not provide a stable identity.")
                    projected = {"creates": 0, "updates": 0, "unchanged": 0, "restored": 0}
                    batch_size = settings.ad_sync_batch_size
                    for start in range(0, len(unique), batch_size):
                        if self._cancelled(run):
                            break
                        for item in list(unique.values())[start:start + batch_size]:
                            try:
                                outcome = self._stage_item(run, object_type, item, utcnow(), dry_run=run.dry_run)
                                projected[{"created": "creates", "updated": "updates",
                                           "unchanged": "unchanged", "restored": "restored"}[outcome]] += 1
                            except Exception:
                                logger.exception("AD object staging failed run_id=%s type=%s", run.id, object_type)
                                self._record_error(run, object_type, "persistence", "object_stage_failed",
                                                   "Directory object could not be staged.")
                        run.progress = {
                            **(run.progress or {}), "current_object_type": object_type,
                            "objects_fetched": len(unique),
                            "objects_processed": sum(projected.values()),
                            "pages_processed": result.page_count,
                        }
                        self.db.commit()
                        self._publish("ad_sync_progress", run, progress=run.progress)
                    setattr(run, f"{object_type}s_seen" if object_type != "computer" else "computers_seen", len(unique))
                    run.created_objects += projected["creates"]
                    run.updated_objects += projected["updates"]
                    run.unchanged_objects += projected["unchanged"]
                    run.restored_objects += projected["restored"]
                    per_type = dict(run.per_type_status or {})
                    per_type[object_type] = {
                        "status": "partial" if result.truncated else "completed",
                        "seen": len(unique), "pages": result.page_count,
                        **projected, "warnings": result.warnings,
                    }
                    run.per_type_status = per_type
                    if run.dry_run:
                        dry = dict(run.dry_run_results or {})
                        dry[object_type] = projected
                        run.dry_run_results = dry
                    if result.truncated:
                        had_partial = True
                    elif run.sync_mode == "full" and not run.dry_run and not run.cancel_requested_at:
                        missing = self._mark_missing(run, object_type, utcnow())
                        run.missing_objects += missing
                        per_type[object_type]["missing"] = missing
                        run.per_type_status = per_type
                    self._publish("ad_sync_object_type_completed", run, object_type=object_type,
                                  result=per_type[object_type])
                    self.db.commit()
                except LdapError as error:
                    had_partial = True
                    self._record_error(run, object_type, "query", error.category,
                                       error.safe_message, retryable=error.retryable)
                    per_type = dict(run.per_type_status or {})
                    per_type[object_type] = {"status": "failed", "error": error.category}
                    run.per_type_status = per_type
                    self.db.commit()
            if run.status == "running":
                target = "partial" if had_partial or run.errors_count else "completed"
                self._transition(run, target)
            if run.status == "completed" and not run.dry_run:
                checkpoint_after = dict(config.checkpoints or {})
                completed_at = utcnow().isoformat()
                for object_type in run.object_types:
                    checkpoint_after[object_type] = completed_at
                config.checkpoints = checkpoint_after
                run.checkpoint_after = checkpoint_after
                self._audit(run, actor.username, "AD_SYNC_CHECKPOINT_UPDATED",
                            "Successful synchronization checkpoints were advanced.")
        except LdapError as error:
            self._record_error(run, None, "connection", error.category, error.safe_message,
                               retryable=error.retryable)
            self._transition(run, "failed")
            run.error_summary = error.safe_message
        except Exception:
            logger.exception("AD synchronization failed run_id=%s", run.id)
            self.db.rollback()
            run = self.db.get(ActiveDirectorySyncRun, run_id)
            if run and run.status == "running":
                self._record_error(run, None, "orchestration", "sync_failed",
                                   "Directory synchronization failed safely.")
                self._transition(run, "failed")
                run.error_summary = "Directory synchronization failed safely."
        finally:
            if client:
                client.close()
            if run:
                run.completed_at = utcnow()
                run.duration_ms = int((monotonic() - started) * 1000)
                action = {
                    "completed": "AD_SYNC_COMPLETED", "partial": "AD_SYNC_PARTIAL",
                    "failed": "AD_SYNC_FAILED", "cancelled": "AD_SYNC_CANCELLED",
                }.get(run.status, "AD_SYNC_FAILED")
                self._audit(run, actor.username, action, f"AD staging synchronization ended with status {run.status}.")
                self.db.commit()
                self._publish(f"ad_sync_{run.status}", run, progress=run.progress)
                self._notify_admin(run)
                self.db.refresh(run)
        return run

    def cancel(self, run_id: str, actor: User) -> ActiveDirectorySyncRun:
        run = self.db.get(ActiveDirectorySyncRun, run_id)
        if not run:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Synchronization run was not found.")
        if run.status not in ACTIVE_STATUSES:
            raise HTTPException(status.HTTP_409_CONFLICT, "Only active synchronization runs can be cancelled.")
        if run.cancel_requested_at:
            return run
        run.cancel_requested_at = utcnow()
        self._audit(run, actor.username, "AD_SYNC_CANCEL_REQUESTED", "Cooperative sync cancellation requested.")
        self.db.commit()
        self.db.refresh(run)
        return run
