import logging

from app.services.email_service import send_email
from app.services.settings_service import read_bundle

logger = logging.getLogger(__name__)


def notify_snmp(db, subject: str, body: str) -> None:
    try:
        config = read_bundle(db)["notifications"]
        if config.get("email_notifications") and config.get("critical_alerts"):
            send_email(subject, body, recipient=config.get("recipient_email"))
    except Exception:
        logger.exception("SNMP grouped notification failed")
