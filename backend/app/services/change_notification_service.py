import logging

from app.services.email_service import send_email
from app.services.settings_service import read_bundle

logger = logging.getLogger(__name__)


def notify_change(db, subject: str, body: str) -> None:
    try:
        config = read_bundle(db)["notifications"]
        if config.get("email_notifications") and config.get("recipient_email"):
            send_email(subject, body, recipient=config["recipient_email"])
    except Exception:
        logger.exception("Grouped change-management notification failed")
