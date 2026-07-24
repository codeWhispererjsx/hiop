import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.db.database import SessionLocal
from app.core.config import settings
from app.models.active_directory import (
    ActiveDirectoryConnection,
    ActiveDirectorySyncConfiguration,
    ActiveDirectorySyncRun,
)
from app.services.network_service import scan_all_devices


scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)
AD_JOB_PREFIX = "active_directory_sync_"


def ad_sync_job_id(connection_id: str) -> str:
    return f"{AD_JOB_PREFIX}{connection_id}"


def _ad_schedulable(connection, config) -> bool:
    return bool(
        settings.active_directory_enabled
        and connection.enabled
        and config
        and config.enabled
        and (config.sync_users_enabled or config.sync_computers_enabled or config.sync_groups_enabled)
        and (connection.authentication_method == "anonymous" or connection.encrypted_bind_secret)
    )


def register_ad_sync_job(connection_id: str, interval_minutes: int | None = None) -> bool:
    if not settings.scheduler_enabled:
        return False
    db = SessionLocal()
    try:
        connection = db.get(ActiveDirectoryConnection, connection_id)
        config = db.scalar(select(ActiveDirectorySyncConfiguration).where(
            ActiveDirectorySyncConfiguration.connection_id == connection_id
        ))
        if not connection or not _ad_schedulable(connection, config):
            remove_ad_sync_job(connection_id)
            return False
        if not scheduler.running:
            scheduler.start()
        scheduler.add_job(
            scheduled_ad_sync,
            trigger="interval",
            minutes=max(settings.ad_minimum_sync_interval_minutes,
                        interval_minutes or config.sync_interval_minutes),
            id=ad_sync_job_id(connection_id),
            args=[connection_id],
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        logger.info("Registered AD sync job connection_id=%s", connection_id)
        return True
    finally:
        db.close()


def update_ad_sync_job(connection_id: str) -> bool:
    return register_ad_sync_job(connection_id)


def remove_ad_sync_job(connection_id: str) -> bool:
    job = scheduler.get_job(ad_sync_job_id(connection_id))
    if job:
        scheduler.remove_job(job.id)
        logger.info("Removed AD sync job connection_id=%s", connection_id)
        return True
    return False


def recover_stale_ad_runs(db=None) -> int:
    owns_session = db is None
    db = db or SessionLocal()
    try:
        threshold = datetime.now(timezone.utc) - timedelta(
            minutes=settings.ad_sync_stale_run_timeout_minutes
        )
        stale = db.scalars(select(ActiveDirectorySyncRun).where(
            ActiveDirectorySyncRun.status.in_(("pending", "running")),
            ActiveDirectorySyncRun.started_at < threshold,
        )).all()
        for run in stale:
            run.status = "failed"
            run.completed_at = datetime.now(timezone.utc)
            run.error_summary = "Recovered stale synchronization after scheduler startup."
        if stale:
            db.commit()
            logger.warning("Recovered stale AD sync runs count=%s", len(stale))
        return len(stale)
    finally:
        if owns_session:
            db.close()


def reconcile_ad_sync_jobs(db=None) -> dict[str, int]:
    owns_session = db is None
    db = db or SessionLocal()
    registered = removed = 0
    try:
        connections = db.scalars(select(ActiveDirectoryConnection)).all()
        configured_ids = set()
        for connection in connections:
            config = db.scalar(select(ActiveDirectorySyncConfiguration).where(
                ActiveDirectorySyncConfiguration.connection_id == connection.id
            ))
            if _ad_schedulable(connection, config):
                configured_ids.add(str(connection.id))
                if register_ad_sync_job(str(connection.id), config.sync_interval_minutes):
                    registered += 1
            elif remove_ad_sync_job(str(connection.id)):
                removed += 1
        for job in list(scheduler.get_jobs()):
            if job.id.startswith(AD_JOB_PREFIX):
                connection_id = job.id.removeprefix(AD_JOB_PREFIX)
                if connection_id not in configured_ids:
                    scheduler.remove_job(job.id)
                    removed += 1
        return {"registered": registered, "removed": removed}
    finally:
        if owns_session:
            db.close()


def scheduled_ad_sync(connection_id: str):
    db = SessionLocal()
    try:
        connection = db.get(ActiveDirectoryConnection, connection_id)
        config = db.scalar(select(ActiveDirectorySyncConfiguration).where(
            ActiveDirectorySyncConfiguration.connection_id == connection_id
        ))
        if not connection or not _ad_schedulable(connection, config):
            remove_ad_sync_job(connection_id)
            return
        object_types = [
            name for name, enabled in (
                ("user", config.sync_users_enabled),
                ("computer", config.sync_computers_enabled),
                ("group", config.sync_groups_enabled),
            ) if enabled
        ]
        from app.services.active_directory_sync_service import ActiveDirectorySynchronizationService
        ActiveDirectorySynchronizationService(db).start(
            connection_id,
            SimpleNamespace(id=None, username="scheduler"),
            sync_mode=settings.ad_sync_default_mode,
            dry_run=config.dry_run_default,
            object_types=object_types,
            limit=settings.ad_maximum_objects_per_sync,
        )
    except Exception:
        db.rollback()
        logger.exception("Scheduled AD sync failed connection_id=%s", connection_id)
    finally:
        db.close()


def configure_scheduler(enabled: bool, interval_minutes: int) -> None:
    from app.core.config import settings
    if not settings.scheduler_enabled:
        return
    if not scheduler.running:
        scheduler.start()
    if not enabled:
        if scheduler.get_job("automatic_network_scan"):
            scheduler.remove_job("automatic_network_scan")
        return
    scheduler.add_job(scheduled_network_scan, trigger="interval", minutes=interval_minutes, id="automatic_network_scan", replace_existing=True, max_instances=1)


def configure_discovery_scheduler(enabled: bool, interval_minutes: int) -> None:
    from app.core.config import settings
    if not settings.scheduler_enabled:
        return
    if not scheduler.running:
        scheduler.start()
    if not enabled:
        if scheduler.get_job("automatic_discovery"):
            scheduler.remove_job("automatic_discovery")
        return
    scheduler.add_job(
        scheduled_discovery,
        trigger="interval",
        minutes=interval_minutes,
        id="automatic_discovery",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )


def scheduled_network_scan():
    db = SessionLocal()

    try:
        result = scan_all_devices(db)

        logger.info("Automatic network scan completed total=%s online=%s offline=%s", result["total_devices"], result["online"], result["offline"])

    except Exception:
        db.rollback()
        logger.exception("Automatic network scan failed")

    finally:
        db.close()


def scheduled_discovery():
    db = SessionLocal()
    try:
        from app.discovery.network import parse_networks
        from app.services.discovery_service import DiscoveryService
        from app.services.settings_service import read_discovery
        config = read_discovery(db)
        if not config["enabled"]:
            return
        for network in parse_networks(config["authorized_cidr_ranges"]):
            DiscoveryService(db, config=config).discover_range(
                str(network), trigger_type="scheduled", audit_actor="scheduler"
            )
    except Exception:
        db.rollback()
        logger.exception("Automatic discovery failed")
    finally:
        db.close()


def start_scheduler():
    if not settings.scheduler_enabled:
        logger.info("HIOP scheduler disabled by configuration")
        return
    if scheduler.running:
        return

    scheduler.start()
    db = SessionLocal()
    try:
        from app.models.system_setting import SystemSetting
        values = {row.key: row.value for row in db.query(SystemSetting).filter(SystemSetting.key.in_(["network.automatic_scanning", "network.scan_interval_minutes", "discovery.enabled", "discovery.interval_minutes"])).all()}
        configure_scheduler(values.get("network.automatic_scanning", "true") == "true", max(5, int(values.get("network.scan_interval_minutes", "5"))))
        configure_discovery_scheduler(values.get("discovery.enabled", "false") == "true", max(15, int(values.get("discovery.interval_minutes", "60"))))
        recover_stale_ad_runs(db)
        reconcile_ad_sync_jobs(db)
    finally:
        db.close()
    logger.info("HIOP scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("HIOP scheduler stopped")
