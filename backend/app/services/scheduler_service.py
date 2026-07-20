import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.database import SessionLocal
from app.services.network_service import scan_all_devices


scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)


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
    from app.core.config import settings
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
    finally:
        db.close()
    logger.info("HIOP scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("HIOP scheduler stopped")
