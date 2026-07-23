import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.network_scan import NetworkScan
from app.models.system_setting import SystemSetting
from app.schemas.settings import DiscoverySettings, GeneralSettings, NetworkSettings, NotificationSettings, OrganizationSettings


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
    "import.maximum_import_file_size": "10485760", "import.supported_formats": "csv,xlsx",
    "import.duplicate_matching_enabled": "true", "import.import_batch_size": "500",
    "import.maximum_rows": "10000", "import.maximum_worksheets": "20", "import.preview_rows": "10",
    "import.maximum_columns": "100", "import.maximum_cell_length": "4000",
    "import.exact_match_threshold": "95", "import.strong_match_threshold": "80",
    "import.probable_match_threshold": "60", "import.weak_match_threshold": "35",
    "import.maximum_candidates_per_row": "5", "import.fuzzy_matching_enabled": "true",
    "import.hostname_similarity_threshold": "88", "import.fuzzy_similarity_threshold": "90",
    "import.auto_suggestion_enabled": "true", "import.subnet_mapping_enabled": "true",
    "import.hostname_rule_mapping_enabled": "true", "import.conflict_penalty": "35",
    "import.candidate_recomputation_batch_size": "250", "import.subnet_mapping_rules": "[]",
    "import.hostname_mapping_rules": "[]", "import.hierarchy_aliases": "{}",
    "import.final_import_batch_size": "100", "import.maximum_concurrent_imports": "1",
    "import.allow_reviewed_field_overwrite": "false", "import.rollback_retention_days": "30",
    "import.final_import_retry_limit": "3", "import.execution_result_retention_days": "365",
    "import.import_notification_threshold": "1", "import.execution_lock_timeout_seconds": "900",
}


def _all(db: Session) -> dict[str, str]:
    values = DEFAULTS.copy()
    values.update({row.key: row.value for row in db.query(SystemSetting).all()})
    return values


def _bool(value: str) -> bool:
    return value.lower() == "true"


def _group(values: dict[str, str], prefix: str) -> dict[str, Any]:
    result = {key.removeprefix(prefix + "."): value for key, value in values.items() if key.startswith(prefix + ".")}
    for key in ("automatic_scanning", "exclude_retired_devices", "automatic_alerts", "automatic_offline_tickets", "email_notifications", "device_offline", "device_restored", "ticket_assignment", "critical_alerts", "enabled", "automatic_vendor_lookup", "automatic_hostname_lookup"):
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
        "discovery": read_discovery(db),
        "email": {"configured": configured, "host": "smtp.gmail.com" if settings.email_address else None, "port": 465 if settings.email_address else None, "security": "TLS" if settings.email_address else "Not configured", "credentials_editable": False},
        "security": {"authentication": "JWT bearer token", "access_token_lifetime": f"{settings.access_token_expire_minutes} minutes", "roles": ["admin", "technician"], "inactive_user_login_blocked": True, "failed_login_auditing": False, "refresh_tokens": False, "mfa": False, "session_revocation": False},
        "application": {"product_name": "Hotel IT Operations Portal", "short_name": "HIOP", "frontend_version": "2.0.0-dev", "backend_version": settings.app_version, "api_prefix": settings.api_prefix, "database_type": "PostgreSQL", "environment": settings.environment.title()},
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


def read_import_settings(db: Session) -> dict[str, Any]:
    values = _group(_all(db), "import")
    result = {
        "maximum_import_file_size": int(values["maximum_import_file_size"]),
        "supported_formats": [item.strip() for item in values["supported_formats"].split(",") if item.strip()],
        "duplicate_matching_enabled": _bool(values["duplicate_matching_enabled"]),
        "import_batch_size": int(values["import_batch_size"]),
        "maximum_rows": int(values["maximum_rows"]),
        "maximum_worksheets": int(values["maximum_worksheets"]),
        "preview_rows": int(values["preview_rows"]),
        "maximum_columns": int(values["maximum_columns"]),
        "maximum_cell_length": int(values["maximum_cell_length"]),
    }
    for key in ("exact_match_threshold", "strong_match_threshold", "probable_match_threshold", "weak_match_threshold", "maximum_candidates_per_row", "hostname_similarity_threshold", "fuzzy_similarity_threshold", "conflict_penalty", "candidate_recomputation_batch_size"):
        result[key] = int(values[key])
    for key in ("final_import_batch_size", "maximum_concurrent_imports", "rollback_retention_days", "final_import_retry_limit", "execution_result_retention_days", "import_notification_threshold", "execution_lock_timeout_seconds"):
        result[key] = int(values[key])
    for key in ("fuzzy_matching_enabled", "auto_suggestion_enabled", "subnet_mapping_enabled", "hostname_rule_mapping_enabled"):
        result[key] = _bool(values[key])
    result["allow_reviewed_field_overwrite"] = _bool(values["allow_reviewed_field_overwrite"])
    for key in ("subnet_mapping_rules", "hostname_mapping_rules", "hierarchy_aliases"):
        try: result[key] = json.loads(values[key])
        except (TypeError, ValueError): result[key] = [] if key != "hierarchy_aliases" else {}
    return result


def save_group(db: Session, prefix: str, payload: GeneralSettings | OrganizationSettings | NetworkSettings | NotificationSettings | DiscoverySettings) -> None:
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
