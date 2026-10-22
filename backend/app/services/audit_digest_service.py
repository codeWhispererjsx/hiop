"""Daily, idempotent audit-log email delivery."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.system_setting import OrganizationSetting, SystemSetting
from app.services.audit_service import create_audit_log
from app.services.email_service import send_email
from app.services.settings_service import _all, _group

LAST_SENT_KEY = "notifications.daily_audit_last_sent_date"


def send_daily_audit_digest(db: Session, now: datetime | None = None, organization_id=None) -> dict:
    if organization_id:
        db.info["organization_id"] = organization_id
    values = _all(db); notification = _group(values, "notifications")
    if not notification.get("daily_audit_email"): return {"status": "disabled"}
    recipient = notification.get("recipient_email")
    if not recipient: return {"status": "missing_recipient"}
    try: zone = ZoneInfo(values.get("general.timezone", "UTC"))
    except ZoneInfoNotFoundError: return {"status": "failed", "message": "The configured application time zone is not recognized"}
    local_now = (now or datetime.now(timezone.utc)).astimezone(zone)
    try: hour, minute = (int(part) for part in notification.get("daily_audit_time", "23:55").split(":"))
    except (TypeError, ValueError): return {"status": "failed", "message": "The daily audit delivery time must use HH:MM"}
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return {"status": "failed", "message": "The daily audit delivery time must use HH:MM"}
    if local_now.time() < time(hour, minute): return {"status": "not_due"}
    today = local_now.date().isoformat()
    marker_key = LAST_SENT_KEY
    if organization_id:
        marker = db.query(OrganizationSetting).filter_by(
            organization_id=organization_id, key=LAST_SENT_KEY
        ).first()
    else:
        marker = db.get(SystemSetting, marker_key)
    if marker and marker.value == today: return {"status": "already_sent"}
    local_start = datetime.combine(local_now.date(), time.min, zone)
    audit_query = db.query(AuditLog).filter(AuditLog.created_at >= local_start.astimezone(timezone.utc))
    if organization_id:
        audit_query = audit_query.filter(AuditLog.organization_id == organization_id)
    rows = audit_query.order_by(AuditLog.created_at).all()
    lines = [f"HIOP daily audit log — {today}", f"Recorded actions: {len(rows)}", ""]
    lines.extend(f"{row.created_at.astimezone(zone):%H:%M:%S} | {row.actor} | {row.action} | {row.entity_type}:{row.entity_id} | {row.description}" for row in rows)
    if not rows: lines.append("No audit activity was recorded today.")
    delivery = send_email(
        f"HIOP daily audit log — {today}",
        "\n".join(lines),
        recipient,
        notification_type="daily_audit",
        organization_id=organization_id,
    )
    delivery_status = getattr(delivery.get("status"), "value", delivery.get("status"))
    if str(delivery_status).casefold() != "sent":
        return {
            "status": "failed",
            "message": str(delivery.get("safe_message") or delivery.get("message") or "Email delivery failed")[:500],
        }
    if marker is None:
        if organization_id:
            marker = OrganizationSetting(organization_id=organization_id, key=LAST_SENT_KEY, value=today)
        else:
            marker = SystemSetting(key=LAST_SENT_KEY, value=today)
        db.add(marker)
    else: marker.value = today
    create_audit_log(db, "scheduler", "DAILY_AUDIT_EMAIL_SENT", "AuditDigest", today, f"Sent {len(rows)} audit records to the configured recipient", organization_id=organization_id)
    db.commit()
    return {"status": "sent", "records": len(rows), "date": today}
