import logging

from app.services.email_service import send_email
from app.services.settings_service import read_bundle

logger = logging.getLogger(__name__)


def notify_knowledge(db, subject: str, body: str) -> None:
    """Send one settings-controlled, grouped operational knowledge notice."""
    try:
        config = read_bundle(db)["notifications"]
        if config.get("email_notifications") and config.get("recipient_email"):
            send_email(subject, body, recipient=config["recipient_email"])
    except Exception:
        logger.exception("Knowledge grouped notification failed")
