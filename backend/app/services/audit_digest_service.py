"""Daily, idempotent audit-log email delivery."""
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.system_setting import SystemSetting
from app.services.audit_service import create_audit_log
from app.services.email_service import send_email
from app.services.settings_service import _all, _group

LAST_SENT_KEY = "notifications.daily_audit_last_sent_date"


def send_daily_audit_digest(db: Session, now: datetime | None = None) -> dict:
    values = _all(db); notification = _group(values, "notifications")
    if not notification.get("daily_audit_email"): return {"status": "disabled"}
    recipient = notification.get("recipient_email")
    if not recipient: return {"status": "missing_recipient"}
    try: zone = ZoneInfo(values.get("general.timezone", "UTC"))
    except ZoneInfoNotFoundError: zone = timezone.utc
    local_now = (now or datetime.now(timezone.utc)).astimezone(zone)
    hour, minute = (int(part) for part in notification.get("daily_audit_time", "23:55").split(":"))
    if local_now.time() < time(hour, minute): return {"status": "not_due"}
    today = local_now.date().isoformat()
    marker = db.get(SystemSetting, LAST_SENT_KEY)
    if marker and marker.value == today: return {"status": "already_sent"}
    local_start = datetime.combine(local_now.date(), time.min, zone)
    rows = db.query(AuditLog).filter(AuditLog.created_at >= local_start.astimezone(timezone.utc)).order_by(AuditLog.created_at).all()
    lines = [f"HIOP daily audit log — {today}", f"Recorded actions: {len(rows)}", ""]
    lines.extend(f"{row.created_at.astimezone(zone):%H:%M:%S} | {row.actor} | {row.action} | {row.entity_type}:{row.entity_id} | {row.description}" for row in rows)
    if not rows: lines.append("No audit activity was recorded today.")
    send_email(f"HIOP daily audit log — {today}", "\n".join(lines), recipient)
    if marker is None: marker = SystemSetting(key=LAST_SENT_KEY, value=today); db.add(marker)
    else: marker.value = today
    create_audit_log(db, "scheduler", "DAILY_AUDIT_EMAIL_SENT", "AuditDigest", today, f"Sent {len(rows)} audit records to the configured recipient")
    db.commit()
    return {"status": "sent", "records": len(rows), "date": today}
