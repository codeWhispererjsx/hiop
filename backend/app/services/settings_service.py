from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.network_scan import NetworkScan
from app.models.system_setting import SystemSetting
from app.schemas.settings import GeneralSettings, NetworkSettings, NotificationSettings, OrganizationSettings


DEFAULTS = {
    "general.application_name": "Hotel IT Operations Portal", "general.short_name": "HIOP", "general.timezone": "Africa/Lagos",
    "general.date_format": "DD/MM/YYYY", "general.time_format": "24-hour", "general.default_page_size": "25",
    "general.default_landing_page": "/dashboard", "general.support_email": "",
    "organization.organization_name": "Hotel IT Operations", "organization.property_name": "Hotel IT Operations",
    "organization.it_department_name": "Information Technology", "organization.address": "", "organization.city": "",
    "organization.country": "", "organization.support_email": "", "organization.support_phone": "",
    "network.approved_network": "10.50.20.0/24", "network.automatic_scanning": "true", "network.scan_interval_minutes": "5",
    "network.ping_timeout_seconds": "5", "network.max_concurrent_workers": "8", "network.exclude_retired_devices": "true",
    "network.automatic_alerts": "true", "network.automatic_offline_tickets": "true", "network.offline_threshold": "3",
    "notifications.email_notifications": "false", "notifications.device_offline": "true", "notifications.device_restored": "true",
    "notifications.ticket_assignment": "true", "notifications.critical_alerts": "true",
    "notifications.sender_display_name": "HIOP Operations", "notifications.recipient_email": "",
    "discovery.enabled": "false", "discovery.authorized_cidr_ranges": "10.50.20.0/24", "discovery.ignore_ranges": "",
    "discovery.interval_minutes": "60", "discovery.ping_timeout_seconds": "2", "discovery.concurrency_limit": "10",
    "discovery.max_hosts_per_run": "256", "discovery.automatic_vendor_lookup": "true", "discovery.automatic_hostname_lookup": "true",
    "discovery.admin_notification_threshold": "5",
}


def _all(db: Session) -> dict[str, str]:
    values = DEFAULTS.copy()
    values.update({row.key: row.value for row in db.query(SystemSetting).all()})
    return values


def _bool(value: str) -> bool:
    return value.lower() == "true"


def _group(values: dict[str, str], prefix: str) -> dict[str, Any]:
    result = {key.removeprefix(prefix + "."): value for key, value in values.items() if key.startswith(prefix + ".")}
    for key in ("automatic_scanning", "exclude_retired_devices", "automatic_alerts", "automatic_offline_tickets", "email_notifications", "device_offline", "device_restored", "ticket_assignment", "critical_alerts"):
        if key in result: result[key] = _bool(result[key])
    for key in ("default_page_size", "scan_interval_minutes", "ping_timeout_seconds", "max_concurrent_workers", "offline_threshold"):
        if key in result: result[key] = int(result[key])
    for key in ("support_email", "recipient_email"):
        if result.get(key) == "": result[key] = None
    return result


def read_bundle(db: Session) -> dict[str, Any]:
    values = _all(db)
    configured = bool(settings.email_address and settings.email_password)
    return {
        "general": _group(values, "general"), "organization": _group(values, "organization"),
        "network": _group(values, "network"), "notifications": _group(values, "notifications"),
        "email": {"configured": configured, "host": "smtp.gmail.com" if settings.email_address else None, "port": 465 if settings.email_address else None, "security": "TLS" if settings.email_address else "Not configured", "credentials_editable": False},
        "security": {"authentication": "JWT bearer token", "access_token_lifetime": f"{settings.access_token_expire_minutes} minutes", "roles": ["admin", "technician"], "inactive_user_login_blocked": True, "failed_login_auditing": False, "refresh_tokens": False, "mfa": False, "session_revocation": False},
        "application": {"product_name": "Hotel IT Operations Portal", "short_name": "HIOP", "frontend_version": "1.0.0", "backend_version": settings.app_version, "api_prefix": settings.api_prefix, "database_type": "PostgreSQL", "environment": settings.environment.title()},
    }


def read_public(db: Session) -> dict[str, Any]:
    values = _all(db)
    return {"application_name": values["general.application_name"], "short_name": values["general.short_name"], "property_name": values["organization.property_name"], "organization_name": values["organization.organization_name"], "support_email": values["organization.support_email"] or values["general.support_email"] or None}


def read_network(db: Session) -> dict[str, Any]:
    return _group(_all(db), "network")


def read_discovery(db: Session) -> dict[str, Any]:
    values = _group(_all(db), "discovery")
    for key in ("enabled", "automatic_vendor_lookup", "automatic_hostname_lookup"):
        values[key] = _bool(values[key])
    for key in (
        "interval_minutes", "ping_timeout_seconds", "concurrency_limit",
        "max_hosts_per_run", "admin_notification_threshold",
    ):
        values[key] = int(values[key])
    return values


def save_group(db: Session, prefix: str, payload: GeneralSettings | OrganizationSettings | NetworkSettings | NotificationSettings) -> None:
    for key, value in payload.model_dump().items():
        setting_key = f"{prefix}.{key}"
        stored = "" if value is None else str(value).lower() if isinstance(value, bool) else str(value)
        row = db.query(SystemSetting).filter(SystemSetting.key == setting_key).first()
        if row: row.value = stored
        else: db.add(SystemSetting(key=setting_key, value=stored))


def health(db: Session) -> dict[str, Any]:
    database = "Connected"
    try: db.execute(text("SELECT 1"))
    except Exception: database = "Unavailable"
    from app.services.scheduler_service import scheduler
    last_scan = db.query(NetworkScan).order_by(NetworkScan.scanned_at.desc()).first() if database == "Connected" else None
    email = "Configured" if settings.email_address and settings.email_password else "Not configured"
    status = "Healthy" if database == "Connected" and (scheduler.running or not settings.scheduler_enabled) else "Degraded"
    scheduler_state = "Disabled" if not settings.scheduler_enabled else "Running" if scheduler.running else "Stopped"
    return {"status": status, "api": "Available", "database": database, "scheduler": scheduler_state, "websocket": "Available", "email": email, "last_scan": last_scan.scanned_at.isoformat() if last_scan else None, "application_version": settings.app_version, "environment": settings.environment.title(), "server_time": datetime.now(timezone.utc).isoformat()}
