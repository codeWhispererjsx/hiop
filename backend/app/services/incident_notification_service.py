import logging

from app.services.email_service import send_email
from app.services.settings_service import read_bundle

logger = logging.getLogger(__name__)


def notify_incident(db, incident, event, summary):
    """Send one grouped incident notification without evidence or source payloads."""
    try:
        config = read_bundle(db)["notifications"]
        if not config.get("email_notifications"):
            return False
        subject = f"[HIOP {incident.priority}] {incident.incident_number}: {event}"
        body = (
            f"{incident.title}\nStatus: {incident.status}\nSeverity: {incident.severity}\n"
            f"{summary}\nOpen the authenticated HIOP incident workspace for details."
        )
        send_email(subject, body, recipient=config.get("recipient_email"))
        return True
    except Exception:
        logger.exception("Grouped incident notification failed incident_id=%s event=%s", incident.id, event)
        return False
