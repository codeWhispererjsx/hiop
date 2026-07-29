import logging
from app.services.email_service import send_email
from app.services.settings_service import read_bundle

logger = logging.getLogger(__name__)


def notify_automation(db, subject, body):
    try:
        config = read_bundle(db)["notifications"]
        if config.get("email_notifications"):
            send_email(subject, body, recipient=config.get("recipient_email"))
    except Exception:
        logger.exception("Automation grouped notification failed")
