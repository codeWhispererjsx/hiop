import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.db.database import SessionLocal
from app.services.network_service import scan_all_devices


scheduler = BackgroundScheduler()
logger = logging.getLogger(__name__)


def configure_scheduler(enabled: bool, interval_minutes: int) -> None:
    if not scheduler.running:
        scheduler.start()
    if not enabled:
        if scheduler.get_job("automatic_network_scan"):
            scheduler.remove_job("automatic_network_scan")
        return
    scheduler.add_job(scheduled_network_scan, trigger="interval", minutes=interval_minutes, id="automatic_network_scan", replace_existing=True, max_instances=1)


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


def start_scheduler():
    if scheduler.running:
        return

    scheduler.start()
    db = SessionLocal()
    try:
        from app.models.system_setting import SystemSetting
        values = {row.key: row.value for row in db.query(SystemSetting).filter(SystemSetting.key.in_(["network.automatic_scanning", "network.scan_interval_minutes"])).all()}
        configure_scheduler(values.get("network.automatic_scanning", "true") == "true", max(5, int(values.get("network.scan_interval_minutes", "5"))))
    finally:
        db.close()
    logger.info("HIOP scheduler started")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("HIOP scheduler stopped")
