from apscheduler.schedulers.background import BackgroundScheduler

from app.db.database import SessionLocal
from app.services.network_service import scan_all_devices


scheduler = BackgroundScheduler()


def scheduled_network_scan():
    db = SessionLocal()

    try:
        result = scan_all_devices(db)

        print(
            "Automatic network scan completed:",
            f"total={result['total_devices']},",
            f"online={result['online']},",
            f"offline={result['offline']}"
        )

    except Exception as exc:
        db.rollback()
        print(f"Automatic network scan failed: {exc}")

    finally:
        db.close()


def start_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        scheduled_network_scan,
        trigger="interval",
        minutes=5,
        id="automatic_network_scan",
        replace_existing=True,
        max_instances=1
    )

    scheduler.start()
    print("HIOP scheduler started.")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        print("HIOP scheduler stopped.")